package com.visionflow.dji.bridge

import java.net.URI

data class DjiBridgeRuntimeConfig(
    val edgeAiBaseUrl: String,
    val droneId: Long,
    val sourceId: String,
) {
    val normalizedEdgeAiBaseUrl: String = normalizeBaseUrl(edgeAiBaseUrl)
    val normalizedSourceId: String = sourceId.trim()

    init {
        require(droneId > 0) {
            "droneId must be greater than zero"
        }
        require(normalizedSourceId.isNotEmpty()) {
            "sourceId must not be blank"
        }
        require(normalizedSourceId.length <= 100) {
            "sourceId must be at most 100 characters"
        }
    }

    companion object {
        fun normalizeSessionId(sessionId: String): String {
            val normalized = sessionId.trim()
            require(normalized.isNotEmpty()) {
                "sessionId must not be blank"
            }
            require(normalized.length <= 36) {
                "sessionId must be at most 36 characters"
            }
            return normalized
        }

        private fun normalizeBaseUrl(value: String): String {
            val normalized = value.trim()
            require(normalized.isNotEmpty()) {
                "edgeAiBaseUrl must not be blank"
            }

            val uri =
                try {
                    URI(normalized)
                } catch (error: Exception) {
                    throw IllegalArgumentException(
                        "edgeAiBaseUrl must be a valid HTTPS URI",
                        error,
                    )
                }

            require(uri.scheme.equals("https", ignoreCase = true)) {
                "edgeAiBaseUrl must use HTTPS"
            }
            require(!uri.host.isNullOrBlank()) {
                "edgeAiBaseUrl must include a host"
            }
            require(uri.userInfo == null) {
                "edgeAiBaseUrl must not contain user info"
            }
            require(uri.query == null && uri.fragment == null) {
                "edgeAiBaseUrl must not contain query or fragment"
            }
            require(uri.path.isNullOrEmpty() || uri.path == "/") {
                "edgeAiBaseUrl must not contain an application path"
            }
            require(uri.port == -1 || uri.port in 1..65_535) {
                "edgeAiBaseUrl port must be in 1..65535"
            }

            return URI(
                "https",
                null,
                uri.host,
                uri.port,
                null,
                null,
                null,
            ).toString()
                .trimEnd('/')
        }
    }
}
