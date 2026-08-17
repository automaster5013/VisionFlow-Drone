package com.visionflow.dji.bridge

import android.app.Application
import android.content.Context

class VisionFlowDjiApplication : Application() {

    override fun attachBaseContext(base: Context?) {
        super.attachBaseContext(base)
        com.cySdkyc.clx.Helper.install(this)
    }

    override fun onCreate() {
        super.onCreate()
        DjiSdkBootstrap.start(this)
    }
}
