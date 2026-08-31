package com.visionflow.dji.bridge

import org.junit.Assert.assertEquals
import org.junit.Assert.fail
import org.junit.Test

class DjiBridgeRuntimeConfigTest {
    @Test
    fun acceptsAndNormalizesHttpsLanEndpoint() {
        val config =
            DjiBridgeRuntimeConfig(
                edgeAiBaseUrl=" https://192.168.46.7:3443/ ",
                droneId=1,
                sourceId=" dji-mini4pro-001 ",
                sessionId="session-001",
            )

        assertEquals(
            "https://192.168.46.7:3443",
            config.normalizedEdgeAiBaseUrl,
        )
        assertEquals(
            "dji-mini4pro-001",
            config.normalizedSourceId,
        )
        assertEquals(
            "session-001",
            config.normalizedSessionId,
        )
    }

    @Test
    fun rejectsCleartextAndApplicationPaths() {
        expectInvalid {
            DjiBridgeRuntimeConfig(
                edgeAiBaseUrl="http://192.168.46.7:8000",
                droneId=1,
                sourceId="dji-test",
                sessionId="session-001",
            )
        }
        expectInvalid {
            DjiBridgeRuntimeConfig(
                edgeAiBaseUrl=(
                    "https://192.168.46.7:3443/api/ingest/dji"
                ),
                droneId=1,
                sourceId="dji-test",
                sessionId="session-001",
            )
        }
    }

    @Test
    fun rejectsQueryFragmentAndUserInfo() {
        expectInvalid {
            DjiBridgeRuntimeConfig(
                edgeAiBaseUrl="https://host:3443?key=value",
                droneId=1,
                sourceId="dji-test",
                sessionId="session-001",
            )
        }
        expectInvalid {
            DjiBridgeRuntimeConfig(
                edgeAiBaseUrl="https://user@host:3443",
                droneId=1,
                sourceId="dji-test",
                sessionId="session-001",
            )
        }
    }

    @Test
    fun validatesDroneSourceAndSessionIdentifiers() {
        expectInvalid {
            DjiBridgeRuntimeConfig(
                edgeAiBaseUrl="https://192.168.46.7:3443",
                droneId=0,
                sourceId="dji-test",
                sessionId="session-001",
            )
        }
        expectInvalid {
            DjiBridgeRuntimeConfig(
                edgeAiBaseUrl="https://192.168.46.7:3443",
                droneId=1,
                sourceId="  ",
                sessionId="session-001",
            )
        }
        expectInvalid {
            DjiBridgeRuntimeConfig.normalizeSessionId("")
        }
        expectInvalid {
            DjiBridgeRuntimeConfig.normalizeSessionId(
                "s".repeat(37),
            )
        }

        assertEquals(
            "session-001",
            DjiBridgeRuntimeConfig.normalizeSessionId(
                " session-001 ",
            ),
        )
    }

    private fun expectInvalid(block: () -> Unit) {
        try {
            block()
            fail("Expected IllegalArgumentException")
        } catch (_: IllegalArgumentException) {
            // Expected validation failure.
        }
    }
}
