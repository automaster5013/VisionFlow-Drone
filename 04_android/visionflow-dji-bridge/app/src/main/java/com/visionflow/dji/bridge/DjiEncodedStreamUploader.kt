package com.visionflow.dji.bridge

import android.net.Uri
import android.util.Log
import java.io.BufferedOutputStream
import java.net.HttpURLConnection
import java.net.URL
import java.util.concurrent.ArrayBlockingQueue
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicLong

class DjiEncodedStreamUploader(
    private val edgeAiBaseUrl: String,
    private val aiInternalKey: String,
    private val droneId: Long,
    private val sourceId: String,
    private val sessionId: String,
    queueCapacity: Int = 256,
) : AutoCloseable {

    enum class Codec(
        val queryValue: String,
        val contentType: String,
    ) {
        H264("H264", "video/h264"),
        H265("H265", "video/h265"),
    }

    private val lock = Any()
    private val queue = ArrayBlockingQueue<ByteArray>(queueCapacity)
    private val transmittedPackets = AtomicLong()
    private val transmittedBytes = AtomicLong()
    private val queueOverflows = AtomicLong()

    @Volatile
    private var running = false

    @Volatile
    private var connection: HttpURLConnection? = null

    private var worker: Thread? = null

    init {
        require(queueCapacity > 0) {
            "queueCapacity must be greater than zero"
        }
        require(droneId > 0) {
            "droneId must be greater than zero"
        }
        require(sourceId.isNotBlank()) {
            "sourceId must not be blank"
        }
        require(sessionId.isNotBlank()) {
            "sessionId must not be blank"
        }
    }

    fun start(codec: Codec) {
        synchronized(lock) {
            check(!running) {
                "DJI encoded stream uploader is already running"
            }

            queue.clear()
            running = true
            worker =
                Thread(
                    { runUpload(codec) },
                    "visionflow-dji-upload",
                ).apply {
                    isDaemon = true
                    start()
                }
        }
    }

    fun offer(
        data: ByteArray,
        length: Int,
    ): Boolean {
        if (!running || length <= 0) {
            return false
        }
        require(length <= data.size) {
            "length exceeds data size"
        }

        val packet = data.copyOf(length)
        val accepted =
            queue.offer(
                packet,
                50,
                TimeUnit.MILLISECONDS,
            )

        if (accepted) {
            return true
        }

        queueOverflows.incrementAndGet()
        running = false
        connection?.disconnect()

        Log.e(
            TAG,
            "DJI_BRIDGE_UPLOAD_OVERFLOW " +
                "queueCapacity=${queue.size + queue.remainingCapacity()}",
        )
        return false
    }

    fun status(): Map<String, Any> =
        mapOf(
            "running" to running,
            "queueDepth" to queue.size,
            "queueCapacity" to (queue.size + queue.remainingCapacity()),
            "transmittedPackets" to transmittedPackets.get(),
            "transmittedBytes" to transmittedBytes.get(),
            "queueOverflows" to queueOverflows.get(),
        )

    override fun close() {
        val thread =
            synchronized(lock) {
                if (!running && worker == null) {
                    return
                }

                running = false
                worker
            }

        thread?.join(5_000)

        if (thread?.isAlive == true) {
            connection?.disconnect()
            thread.join(2_000)
        }
    }

    private fun runUpload(codec: Codec) {
        var current: HttpURLConnection? = null

        try {
            current =
                (URL(buildEndpoint(codec)).openConnection() as HttpURLConnection)
                    .apply {
                        requestMethod = "POST"
                        doOutput = true
                        useCaches = false
                        connectTimeout = 5_000
                        readTimeout = 15_000
                        setChunkedStreamingMode(64 * 1024)
                        setRequestProperty("Accept", "application/json")
                        setRequestProperty(
                            "Content-Type",
                            codec.contentType,
                        )
                        if (aiInternalKey.isNotBlank()) {
                            setRequestProperty(
                                AI_KEY_HEADER,
                                aiInternalKey,
                            )
                        }
                    }

            connection = current

            BufferedOutputStream(current.outputStream).use { output ->
                while (running || queue.isNotEmpty()) {
                    val packet =
                        queue.poll(
                            500,
                            TimeUnit.MILLISECONDS,
                        ) ?: continue

                    output.write(packet)
                    transmittedPackets.incrementAndGet()
                    transmittedBytes.addAndGet(packet.size.toLong())
                }

                output.flush()
            }

            val responseCode = current.responseCode
            val responseStream =
                if (responseCode in 200..299) {
                    current.inputStream
                } else {
                    current.errorStream
                }
            responseStream?.close()

            Log.i(
                TAG,
                "DJI_BRIDGE_UPLOAD_END http=$responseCode " +
                    "codec=${codec.queryValue} " +
                    "packets=${transmittedPackets.get()} " +
                    "bytes=${transmittedBytes.get()} " +
                    "overflows=${queueOverflows.get()}",
            )
        } catch (error: Exception) {
            Log.e(
                TAG,
                "DJI_BRIDGE_UPLOAD_ERROR " +
                    "codec=${codec.queryValue} " +
                    "packets=${transmittedPackets.get()} " +
                    "bytes=${transmittedBytes.get()} " +
                    "overflows=${queueOverflows.get()}",
                error,
            )
        } finally {
            current?.disconnect()
            connection = null
            running = false

            synchronized(lock) {
                worker = null
            }
        }
    }

    private fun buildEndpoint(codec: Codec): String =
        Uri.parse(
            edgeAiBaseUrl.trimEnd('/') + INGEST_PATH,
        ).buildUpon()
            .appendQueryParameter(
                "droneId",
                droneId.toString(),
            )
            .appendQueryParameter(
                "sourceId",
                sourceId,
            )
            .appendQueryParameter(
                "sessionId",
                sessionId,
            )
            .appendQueryParameter(
                "codec",
                codec.queryValue,
            )
            .build()
            .toString()

    companion object {
        private const val TAG = "VisionFlowDJI"
        private const val AI_KEY_HEADER = "X-VisionFlow-AI-Key"
        private const val INGEST_PATH = "/api/ingest/dji/stream"
    }
}
