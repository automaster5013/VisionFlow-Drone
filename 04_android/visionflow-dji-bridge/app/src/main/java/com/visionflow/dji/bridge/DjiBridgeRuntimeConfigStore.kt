package com.visionflow.dji.bridge

import android.content.Context

data class DjiBridgeRuntimeSnapshot(
    val profileConfigured: Boolean,
    val bridgeKeyConfigured: Boolean,
    val ready: Boolean,
    val edgeAiBaseUrl: String?,
    val droneId: Long?,
    val sourceId: String?,
)

class DjiBridgeRuntimeConfigStore private constructor(
    context: Context,
    storageSuffix: String,
) {
    constructor(context: Context) : this(
        context,
        "",
    )

    private val normalizedStorageSuffix =
        DjiBridgeSecretStore.validateStorageSuffix(storageSuffix)
    private val appContext = context.applicationContext
    private val preferences =
        appContext.getSharedPreferences(
            PREFERENCES_NAME + normalizedStorageSuffix,
            Context.MODE_PRIVATE,
        )
    private val secretStore =
        DjiBridgeSecretStore(
            appContext,
            normalizedStorageSuffix,
        )

    @Synchronized
    fun save(
        config: DjiBridgeRuntimeConfig,
        djiBridgeKey: String,
    ) {
        saveCredential(djiBridgeKey)
        saveProfile(config)
    }

    @Synchronized
    fun saveProfile(
        config: DjiBridgeRuntimeConfig,
    ) {
        val committed =
            preferences.edit()
                .putString(
                    KEY_EDGE_AI_BASE_URL,
                    config.normalizedEdgeAiBaseUrl,
                )
                .putLong(
                    KEY_DRONE_ID,
                    config.droneId,
                )
                .putString(
                    KEY_SOURCE_ID,
                    config.normalizedSourceId,
                )
                .commit()

        check(committed) {
            "DJI bridge runtime profile could not be persisted"
        }
    }

    @Synchronized
    fun saveCredential(djiBridgeKey: String) {
        secretStore.save(djiBridgeKey)
    }

    @Synchronized
    fun loadConfig(): DjiBridgeRuntimeConfig? {
        if (
            !preferences.contains(KEY_EDGE_AI_BASE_URL) ||
            !preferences.contains(KEY_DRONE_ID) ||
            !preferences.contains(KEY_SOURCE_ID)
        ) {
            return null
        }

        val edgeAiBaseUrl =
            preferences.getString(
                KEY_EDGE_AI_BASE_URL,
                null,
            ) ?: return null
        val sourceId =
            preferences.getString(
                KEY_SOURCE_ID,
                null,
            ) ?: return null

        return DjiBridgeRuntimeConfig(
            edgeAiBaseUrl=edgeAiBaseUrl,
            droneId=preferences.getLong(
                KEY_DRONE_ID,
                0,
            ),
            sourceId=sourceId,
        )
    }

    @Synchronized
    fun snapshot(): DjiBridgeRuntimeSnapshot {
        val config = loadConfig()
        val secretConfigured = secretStore.isConfigured()

        return DjiBridgeRuntimeSnapshot(
            profileConfigured=config != null,
            bridgeKeyConfigured=secretConfigured,
            ready=config != null && secretConfigured,
            edgeAiBaseUrl=config?.normalizedEdgeAiBaseUrl,
            droneId=config?.droneId,
            sourceId=config?.normalizedSourceId,
        )
    }

    @Synchronized
    fun createUploader(
        sessionId: String,
        queueCapacity: Int = DEFAULT_QUEUE_CAPACITY,
    ): DjiEncodedStreamUploader {
        require(queueCapacity > 0) {
            "queueCapacity must be greater than zero"
        }

        val config =
            loadConfig()
                ?: error(
                    "DJI bridge runtime profile is not configured",
                )
        val djiBridgeKey =
            secretStore.load()
                ?: error(
                    "DJI bridge credential is not configured",
                )

        return DjiEncodedStreamUploader(
            edgeAiBaseUrl=config.normalizedEdgeAiBaseUrl,
            djiBridgeKey=djiBridgeKey,
            droneId=config.droneId,
            sourceId=config.normalizedSourceId,
            sessionId=(
                DjiBridgeRuntimeConfig.normalizeSessionId(
                    sessionId,
                )
            ),
            queueCapacity=queueCapacity,
        )
    }

    @Synchronized
    fun clear() {
        check(preferences.edit().clear().commit()) {
            "DJI bridge runtime profile could not be cleared"
        }
        secretStore.clear()
    }

    companion object {
        internal fun isolatedForDiagnostics(
            context: Context,
            storageSuffix: String,
        ): DjiBridgeRuntimeConfigStore =
            DjiBridgeRuntimeConfigStore(
                context,
                storageSuffix,
            )

        private const val PREFERENCES_NAME =
            "visionflow_dji_bridge_runtime"
        private const val KEY_EDGE_AI_BASE_URL =
            "edge_ai_base_url"
        private const val KEY_DRONE_ID = "drone_id"
        private const val KEY_SOURCE_ID = "source_id"
        private const val DEFAULT_QUEUE_CAPACITY = 256
    }
}
