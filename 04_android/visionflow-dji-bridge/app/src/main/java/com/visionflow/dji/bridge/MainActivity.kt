package com.visionflow.dji.bridge

import android.app.Activity
import android.app.AlertDialog
import android.graphics.Typeface
import android.os.Build
import android.os.Bundle
import android.text.InputType
import android.text.method.PasswordTransformationMethod
import android.view.Gravity
import android.view.View
import android.view.ViewGroup
import android.view.WindowManager
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView

class MainActivity : Activity() {
    private lateinit var store: DjiBridgeRuntimeConfigStore
    private lateinit var edgeUrlInput: EditText
    private lateinit var droneIdInput: EditText
    private lateinit var sourceIdInput: EditText
    private lateinit var sessionIdInput: EditText
    private lateinit var bridgeKeyInput: EditText
    private lateinit var statusView: TextView
    private lateinit var messageView: TextView

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.addFlags(WindowManager.LayoutParams.FLAG_SECURE)

        store = DjiBridgeRuntimeConfigStore(applicationContext)
        setContentView(buildContent())
        loadSnapshotIntoForm()
    }

    private fun buildContent(): View {
        val content = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(24), dp(20), dp(24), dp(28))
        }

        content.addView(TextView(this).apply {
            text = "VisionFlow DJI Bridge Setup"
            textSize = 24f
            setTypeface(typeface, Typeface.BOLD)
        })
        content.addView(TextView(this).apply {
            text = "DJI MSDK 5.18.0 · HTTPS provisioning"
            textSize = 14f
            setPadding(0, dp(4), 0, dp(20))
        })

        edgeUrlInput = addField(
            content,
            "Edge AI HTTPS URL",
            "https://<EDGE_LAN_IP>:3443",
            InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_URI,
        )
        droneIdInput = addField(
            content,
            "Drone ID",
            "1",
            InputType.TYPE_CLASS_NUMBER,
        )
        sourceIdInput = addField(
            content,
            "Source ID",
            "dji-mini4pro-001",
            InputType.TYPE_CLASS_TEXT,
        )
        sessionIdInput = addField(
            content,
            "Flight Session ID",
            "Backend Flight Session UUID",
            InputType.TYPE_CLASS_TEXT,
        )
        bridgeKeyInput = addField(
            content,
            "DJI Bridge Key",
            "32+ characters; blank keeps existing key",
            InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_PASSWORD,
        ).apply {
            transformationMethod = PasswordTransformationMethod.getInstance()
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                importantForAutofill =
                    View.IMPORTANT_FOR_AUTOFILL_NO_EXCLUDE_DESCENDANTS
            }
        }

        val actions = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            setPadding(0, dp(8), 0, dp(12))
        }
        actions.addView(
            Button(this).apply {
                text = "Save Securely"
                setOnClickListener { saveProvisioning() }
            },
            LinearLayout.LayoutParams(
                0,
                ViewGroup.LayoutParams.WRAP_CONTENT,
                1f,
            ).apply { marginEnd = dp(8) },
        )
        actions.addView(
            Button(this).apply {
                text = "Clear"
                setOnClickListener { confirmClearProvisioning() }
            },
            LinearLayout.LayoutParams(
                0,
                ViewGroup.LayoutParams.WRAP_CONTENT,
                1f,
            ).apply { marginStart = dp(8) },
        )
        content.addView(actions)

        messageView = TextView(this).apply {
            textSize = 14f
            setPadding(0, 0, 0, dp(14))
        }
        content.addView(messageView)

        statusView = TextView(this).apply {
            textSize = 16f
            typeface = Typeface.MONOSPACE
            setPadding(dp(14), dp(14), dp(14), dp(14))
        }
        content.addView(statusView)

        return ScrollView(this).apply {
            addView(
                content,
                ViewGroup.LayoutParams(
                    ViewGroup.LayoutParams.MATCH_PARENT,
                    ViewGroup.LayoutParams.WRAP_CONTENT,
                ),
            )
        }
    }

    private fun addField(
        parent: LinearLayout,
        label: String,
        hint: String,
        inputType: Int,
    ): EditText {
        parent.addView(TextView(this).apply {
            text = label
            textSize = 14f
            setTypeface(typeface, Typeface.BOLD)
            setPadding(0, dp(8), 0, dp(4))
        })

        return EditText(this).apply {
            this.hint = hint
            this.inputType = inputType
            isSingleLine = true
            parent.addView(
                this,
                LinearLayout.LayoutParams(
                    ViewGroup.LayoutParams.MATCH_PARENT,
                    ViewGroup.LayoutParams.WRAP_CONTENT,
                ),
            )
        }
    }

    private fun loadSnapshotIntoForm() {
        try {
            val snapshot = store.snapshot()
            if (snapshot.profileConfigured) {
                loadProfile(snapshot)
            } else {
                droneIdInput.setText(DEFAULT_DRONE_ID.toString())
                sourceIdInput.setText(DEFAULT_SOURCE_ID)
                sessionIdInput.setText("")
            }
            bridgeKeyInput.setText("")
            renderStatus(snapshot)
        } catch (error: Exception) {
            showMessage(
                "Stored provisioning could not be read: ${safeMessage(error)}",
                isError = true,
            )
            renderUnavailableStatus()
        }
    }

    private fun saveProvisioning() {
        try {
            val droneId = droneIdInput.text.toString()
                .trim()
                .toLongOrNull()
                ?: throw IllegalArgumentException(
                    "Drone ID must be a positive integer",
                )

            val config = DjiBridgeRuntimeConfig(
                edgeAiBaseUrl=edgeUrlInput.text.toString(),
                droneId=droneId,
                sourceId=sourceIdInput.text.toString(),
                sessionId=sessionIdInput.text.toString(),
            )

            val bridgeKey = bridgeKeyInput.text.toString()
            val before = store.snapshot()

            if (bridgeKey.isNotEmpty()) {
                store.save(config, bridgeKey)
            } else if (before.bridgeKeyConfigured) {
                store.saveProfile(config)
            } else {
                throw IllegalArgumentException(
                    "DJI Bridge Key is required for first provisioning",
                )
            }

            bridgeKeyInput.setText("")
            val after = store.snapshot()
            DjiCameraStreamBridgeRuntime.refreshProvisioning()
            loadProfile(after)
            renderStatus(after)
            showMessage(
                "Provisioning saved securely. Credential value is hidden.",
                isError = false,
            )
        } catch (error: Exception) {
            showMessage(safeMessage(error), isError = true)
        }
    }

    private fun confirmClearProvisioning() {
        AlertDialog.Builder(this)
            .setTitle("Clear DJI Bridge provisioning?")
            .setMessage(
                "This removes the saved profile, encrypted bridge credential, " +
                    "and its Android Keystore key.",
            )
            .setNegativeButton("Cancel", null)
            .setPositiveButton("Clear") { _, _ -> clearProvisioning() }
            .show()
    }

    private fun clearProvisioning() {
        try {
            store.clear()
            edgeUrlInput.setText("")
            droneIdInput.setText(DEFAULT_DRONE_ID.toString())
            sourceIdInput.setText(DEFAULT_SOURCE_ID)
            sessionIdInput.setText("")
            bridgeKeyInput.setText("")
            DjiCameraStreamBridgeRuntime.refreshProvisioning()
            renderStatus(store.snapshot())
            showMessage("Provisioning cleared.", isError = false)
        } catch (error: Exception) {
            showMessage(
                "Provisioning could not be cleared: ${safeMessage(error)}",
                isError = true,
            )
        }
    }

    private fun loadProfile(snapshot: DjiBridgeRuntimeSnapshot) {
        edgeUrlInput.setText(snapshot.edgeAiBaseUrl.orEmpty())
        droneIdInput.setText(snapshot.droneId?.toString().orEmpty())
        sourceIdInput.setText(snapshot.sourceId.orEmpty())
        sessionIdInput.setText(snapshot.sessionId.orEmpty())
    }

    private fun renderStatus(snapshot: DjiBridgeRuntimeSnapshot) {
        val profile = if (snapshot.profileConfigured) "READY" else "MISSING"
        val credential = if (snapshot.bridgeKeyConfigured) "READY" else "MISSING"
        val session = if (snapshot.sessionId.isNullOrBlank()) "MISSING" else "READY"
        val transport = if (
            snapshot.edgeAiBaseUrl?.startsWith(
                "https://",
                ignoreCase = true,
            ) == true
        ) {
            "HTTPS"
        } else {
            "WAIT"
        }
        val overall = if (snapshot.ready) "READY" else "WAIT"

        statusView.text = buildString {
            appendLine("Runtime     $overall")
            appendLine("Profile     $profile")
            appendLine("Credential  $credential")
            appendLine("Session     $session")
            appendLine("Transport   $transport")
            append("MSDK        WAIT")
        }
    }

    private fun renderUnavailableStatus() {
        statusView.text =
            "Runtime     ERROR\n" +
                "Profile     UNKNOWN\n" +
                "Credential  UNKNOWN\n" +
                "Transport   UNKNOWN\n" +
                "MSDK        WAIT"
    }

    private fun showMessage(message: String, isError: Boolean) {
        messageView.text = if (isError) "ERROR: $message" else message
    }

    private fun safeMessage(error: Exception): String =
        error.message
            ?.take(MAX_ERROR_MESSAGE_LENGTH)
            ?.ifBlank { null }
            ?: error.javaClass.simpleName

    private fun dp(value: Int): Int =
        (value * resources.displayMetrics.density).toInt()

    companion object {
        private const val DEFAULT_DRONE_ID = 1L
        private const val DEFAULT_SOURCE_ID = "dji-mini4pro-001"
        private const val MAX_ERROR_MESSAGE_LENGTH = 180
    }
}
