package com.visionflow.dji.bridge

import android.content.Context
import android.util.Log
import dji.sdk.keyvalue.value.common.ComponentIndexType
import dji.v5.manager.datacenter.MediaDataCenter
import dji.v5.manager.datacenter.camera.StreamInfo
import dji.v5.manager.interfaces.ICameraStreamManager
import java.util.concurrent.atomic.AtomicLong

object DjiCameraStreamBridgeRuntime {
    private val lock = Any()

    @Volatile
    private var started = false

    private var appContext: Context? = null
    private var selectedCamera: ComponentIndexType? = null
    private var uploader: DjiEncodedStreamUploader? = null
    private var uploaderCodec: DjiEncodedStreamUploader.Codec? = null
    private var uploadUnavailableLogged = false
    private val receivedPackets = AtomicLong()
    private val receivedBytes = AtomicLong()

    private val cameraStreamManager
        get() = MediaDataCenter.getInstance().cameraStreamManager

    private val availableCameraListener =
        object : ICameraStreamManager.AvailableCameraUpdatedListener {
            override fun onAvailableCameraUpdated(
                availableCameraList: List<ComponentIndexType>,
            ) {
                handleAvailableCameras(availableCameraList)
            }
        }

    private val receiveStreamListener =
        object : ICameraStreamManager.ReceiveStreamListener {
            override fun onReceiveStream(
                data: ByteArray,
                offset: Int,
                length: Int,
                info: StreamInfo,
            ) {
                handleEncodedPacket(data, offset, length, info)
            }
        }

    fun start(context: Context) {
        synchronized(lock) {
            if (started) return
            appContext = context.applicationContext
            started = true
        }
        cameraStreamManager.addAvailableCameraUpdatedListener(
            availableCameraListener,
        )
        Log.i(TAG, "MSDK_CAMERA_LISTENER_READY")
    }

    fun refreshProvisioning() {
        val previous = synchronized(lock) {
            uploadUnavailableLogged = false
            uploaderCodec = null
            val active = uploader
            uploader = null
            active
        }
        previous?.close()
        Log.i(TAG, "DJI_BRIDGE_PROVISIONING_REFRESH")
    }

    private fun handleAvailableCameras(
        availableCameraList: List<ComponentIndexType>,
    ) {
        val candidate = availableCameraList.firstOrNull {
            it != ComponentIndexType.UNKNOWN
        }
        var previousUploader: DjiEncodedStreamUploader? = null
        var previousCamera: ComponentIndexType? = null
        synchronized(lock) {
            if (!started) return
            if (selectedCamera == candidate) {
                if (candidate != null) {
                    Log.i(TAG, "MSDK_CAMERA_AVAILABLE camera=$candidate count=${availableCameraList.size}")
                }
                return
            }
            previousCamera = selectedCamera
            selectedCamera = candidate
            previousUploader = uploader
            uploader = null
            uploaderCodec = null
            uploadUnavailableLogged = false
            receivedPackets.set(0)
            receivedBytes.set(0)
        }
        if (previousCamera != null) {
            cameraStreamManager.removeReceiveStreamListener(receiveStreamListener)
        }
        previousUploader?.close()
        if (candidate == null) {
            Log.i(TAG, "MSDK_CAMERA_UNAVAILABLE")
            return
        }
        Log.i(TAG, "MSDK_CAMERA_AVAILABLE camera=$candidate count=${availableCameraList.size}")
        cameraStreamManager.addReceiveStreamListener(candidate, receiveStreamListener)
        Log.i(TAG, "MSDK_STREAM_LISTENER_ATTACHED camera=$candidate")
    }

    private fun handleEncodedPacket(
        data: ByteArray,
        offset: Int,
        length: Int,
        info: StreamInfo,
    ) {
        if (length <= 0) return
        val codec = when (info.mimeType) {
            ICameraStreamManager.MimeType.H264 -> DjiEncodedStreamUploader.Codec.H264
            ICameraStreamManager.MimeType.H265 -> DjiEncodedStreamUploader.Codec.H265
            else -> {
                Log.e(TAG, "MSDK_ENCODED_STREAM_UNSUPPORTED mime=${info.mimeType}")
                return
            }
        }
        val activeUploader = ensureUploader(codec) ?: return
        val accepted = try {
            activeUploader.offer(data=data, offset=offset, length=length)
        } catch (error: IllegalArgumentException) {
            Log.e(TAG, "MSDK_ENCODED_STREAM_RANGE_ERROR offset=$offset length=$length size=${data.size}", error)
            false
        }
        if (!accepted) {
            Log.e(TAG, "MSDK_ENCODED_STREAM_UPLOAD_REJECTED codec=${codec.queryValue}")
            resetUploader(activeUploader)
            return
        }
        val packetCount = receivedPackets.incrementAndGet()
        val byteCount = receivedBytes.addAndGet(length.toLong())
        if (packetCount == 1L) {
            Log.i(TAG, "MSDK_ENCODED_STREAM_FIRST camera=${currentCamera()} codec=${codec.queryValue} width=${info.width} height=${info.height} fps=${info.frameRate} keyFrame=${info.isKeyFrame}")
        } else if (packetCount % PROGRESS_EVERY_PACKETS == 0L) {
            Log.i(TAG, "MSDK_ENCODED_STREAM_PROGRESS camera=${currentCamera()} codec=${codec.queryValue} packets=$packetCount bytes=$byteCount")
        }
    }

    private fun ensureUploader(
        codec: DjiEncodedStreamUploader.Codec,
    ): DjiEncodedStreamUploader? {
        var previous: DjiEncodedStreamUploader? = null
        synchronized(lock) {
            if (!started || selectedCamera == null) return null
            val active = uploader
            if (active != null && uploaderCodec == codec) return active
            previous = active
            uploader = null
            uploaderCodec = null
        }
        previous?.close()
        val context = synchronized(lock) { appContext } ?: return null
        val created = try {
            val store = DjiBridgeRuntimeConfigStore(context)
            if (!store.snapshot().ready) {
                logUploadUnavailableOnce("DJI_BRIDGE_WAIT_PROVISIONING")
                return null
            }
            store.createUploader().apply { start(codec) }
        } catch (error: Exception) {
            logUploadUnavailableOnce(
                "DJI_BRIDGE_UPLOAD_START_ERROR type=${error.javaClass.simpleName} message=${safeMessage(error)}",
            )
            return null
        }
        var keep = false
        synchronized(lock) {
            if (started && selectedCamera != null) {
                uploader = created
                uploaderCodec = codec
                uploadUnavailableLogged = false
                keep = true
            }
        }
        if (!keep) {
            created.close()
            return null
        }
        Log.i(TAG, "DJI_BRIDGE_UPLOAD_START camera=${currentCamera()} codec=${codec.queryValue}")
        return created
    }

    private fun resetUploader(expected: DjiEncodedStreamUploader) {
        var removed: DjiEncodedStreamUploader? = null
        synchronized(lock) {
            if (uploader !== expected) return
            removed = uploader
            uploader = null
            uploaderCodec = null
        }
        removed?.close()
    }

    private fun currentCamera(): ComponentIndexType? = synchronized(lock) {
        selectedCamera
    }

    private fun logUploadUnavailableOnce(message: String) {
        val shouldLog = synchronized(lock) {
            if (uploadUnavailableLogged) false else {
                uploadUnavailableLogged = true
                true
            }
        }
        if (shouldLog) Log.w(TAG, message)
    }

    private fun safeMessage(error: Exception): String =
        error.message
            ?.replace('\n', ' ')
            ?.replace('\r', ' ')
            ?.take(MAX_ERROR_MESSAGE_LENGTH)
            ?.ifBlank { null }
            ?: error.javaClass.simpleName

    private const val TAG = "VisionFlowDJI"
    private const val PROGRESS_EVERY_PACKETS = 120L
    private const val MAX_ERROR_MESSAGE_LENGTH = 160
}
