package com.visionflow.dji.bridge

import android.content.Context
import android.util.Log
import dji.v5.common.error.IDJIError
import dji.v5.common.register.DJISDKInitEvent
import dji.v5.manager.SDKManager
import dji.v5.manager.interfaces.SDKManagerCallback

object DjiSdkBootstrap {
    private const val TAG = "VisionFlowDJI"

    fun start(context: Context) {
        Log.i(TAG, "MSDK_INIT_START")
        SDKManager.getInstance().init(context.applicationContext, object : SDKManagerCallback {

            override fun onRegisterSuccess() {
                Log.i(TAG, "MSDK_REGISTER_SUCCESS")
                DjiCameraStreamBridgeRuntime.start(
                    context.applicationContext,
                )
            }

            override fun onRegisterFailure(error: IDJIError) {
                Log.e(TAG, "MSDK_REGISTER_FAILURE error=$error")
            }

            override fun onProductDisconnect(productId: Int) {
                Log.i(TAG, "MSDK_PRODUCT_DISCONNECT id=$productId")
            }

            override fun onProductConnect(productId: Int) {
                Log.i(TAG, "MSDK_PRODUCT_CONNECT id=$productId")
            }

            override fun onProductChanged(productId: Int) {
                Log.i(TAG, "MSDK_PRODUCT_CHANGED id=$productId")
            }

            override fun onInitProcess(event: DJISDKInitEvent, totalProcess: Int) {
                Log.i(TAG, "MSDK_INIT_PROCESS event=$event progress=$totalProcess")
                if (event == DJISDKInitEvent.INITIALIZE_COMPLETE) {
                    Log.i(TAG, "MSDK_INITIALIZE_COMPLETE")
                    SDKManager.getInstance().registerApp()
                    Log.i(TAG, "MSDK_REGISTER_APP_REQUESTED")
                }
            }

            override fun onDatabaseDownloadProgress(current: Long, total: Long) {
                Log.i(TAG, "MSDK_DB_PROGRESS current=$current total=$total")
            }
        })
    }
}
