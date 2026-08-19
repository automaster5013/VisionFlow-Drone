package com.visionflow.dji.bridge

import android.app.Activity
import android.os.Bundle
import android.util.Base64
import android.util.Log
import android.view.Gravity
import android.view.WindowManager
import android.widget.TextView
import java.security.SecureRandom

class DjiProvisioningSelfTestActivity : Activity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.addFlags(WindowManager.LayoutParams.FLAG_SECURE)

        val runId = sanitizeRunId(
            intent.getStringExtra(EXTRA_RUN_ID),
        )
        val result =
            try {
                runSelfTest()
                Log.i(
                    TAG,
                    "DJI_PROVISIONING_SELF_TEST_PASS runId=$runId",
                )
                "Provisioning self-test PASS"
            } catch (error: Exception) {
                Log.e(
                    TAG,
                    "DJI_PROVISIONING_SELF_TEST_FAIL " +
                        "runId=$runId type=${error.javaClass.simpleName} " +
                        "message=${safeMessage(error)}",
                )
                "Provisioning self-test FAIL"
            }

        setContentView(
            TextView(this).apply {
                gravity = Gravity.CENTER
                textSize = 20f
                text = result
            },
        )
    }

    private fun runSelfTest() {
        val store =
            DjiBridgeRuntimeConfigStore.isolatedForDiagnostics(
                applicationContext,
                SELF_TEST_SUFFIX,
            )
        val secretStore =
            DjiBridgeSecretStore(
                applicationContext,
                SELF_TEST_SUFFIX,
            )

        store.clear()

        try {
            val bridgeKey = generateBridgeKey()
            val config =
                DjiBridgeRuntimeConfig(
                    edgeAiBaseUrl=SELF_TEST_EDGE_URL,
                    droneId=SELF_TEST_DRONE_ID,
                    sourceId=SELF_TEST_SOURCE_ID,
                )

            store.save(
                config,
                bridgeKey,
            )

            val snapshot = store.snapshot()
            check(snapshot.ready)
            check(snapshot.profileConfigured)
            check(snapshot.bridgeKeyConfigured)
            check(
                snapshot.edgeAiBaseUrl ==
                    SELF_TEST_EDGE_URL
            )
            check(snapshot.droneId == SELF_TEST_DRONE_ID)
            check(snapshot.sourceId == SELF_TEST_SOURCE_ID)

            val loaded = store.loadConfig()
            check(loaded != null)
            check(
                loaded.normalizedEdgeAiBaseUrl ==
                    SELF_TEST_EDGE_URL
            )
            check(loaded.droneId == SELF_TEST_DRONE_ID)
            check(
                loaded.normalizedSourceId ==
                    SELF_TEST_SOURCE_ID
            )

            val decrypted = secretStore.load()
            check(decrypted == bridgeKey) {
                "Android Keystore credential round-trip mismatch"
            }

            val uploader =
                store.createUploader(
                    sessionId=SELF_TEST_SESSION_ID,
                    queueCapacity=1,
                )
            uploader.close()

            store.clear()

            val cleared = store.snapshot()
            check(!cleared.ready)
            check(!cleared.profileConfigured)
            check(!cleared.bridgeKeyConfigured)
            check(secretStore.load() == null)
        } finally {
            runCatching {
                store.clear()
            }
        }
    }

    private fun generateBridgeKey(): String {
        val bytes = ByteArray(48)
        SecureRandom().nextBytes(bytes)

        return try {
            Base64.encodeToString(
                bytes,
                Base64.URL_SAFE or
                    Base64.NO_WRAP or
                    Base64.NO_PADDING,
            )
        } finally {
            bytes.fill(0)
        }
    }

    private fun sanitizeRunId(value: String?): String {
        val candidate =
            value
                ?.take(MAX_RUN_ID_LENGTH)
                ?.ifBlank { null }
                ?: "manual"

        return candidate.map { character ->
            if (
                character.isLetterOrDigit() ||
                character in "._-"
            ) {
                character
            } else {
                '_'
            }
        }.joinToString("")
    }

    private fun safeMessage(error: Exception): String =
        error.message
            ?.take(MAX_ERROR_MESSAGE_LENGTH)
            ?.replace('\n', ' ')
            ?.replace('\r', ' ')
            ?.ifBlank { null }
            ?: error.javaClass.simpleName

    companion object {
        private const val TAG = "VisionFlowProvisioning"
        private const val EXTRA_RUN_ID = "runId"
        private const val SELF_TEST_SUFFIX = "_adb_self_test"
        private const val SELF_TEST_EDGE_URL =
            "https://127.0.0.1:3443"
        private const val SELF_TEST_DRONE_ID = 1L
        private const val SELF_TEST_SOURCE_ID =
            "dji-adb-self-test"
        private const val SELF_TEST_SESSION_ID =
            "phase3-adb-self-test"
        private const val MAX_RUN_ID_LENGTH = 64
        private const val MAX_ERROR_MESSAGE_LENGTH = 160
    }
}
