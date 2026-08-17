package com.visionflow.dji.bridge

import android.app.Activity
import android.os.Bundle
import android.view.Gravity
import android.widget.TextView

class MainActivity : Activity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        val status = TextView(this).apply {
            gravity = Gravity.CENTER
            textSize = 20f
            text = "VisionFlow DJI Bridge\nDJI MSDK 5.18.0\nScaffold Ready"
        }

        setContentView(status)
    }
}
