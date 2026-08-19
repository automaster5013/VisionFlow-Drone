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
            )

        assertEquals(
            "https://192.168.46.7:3443",
            config.normalizedEdgeAiBaseUrl,
        )
        assertEquals(
            "dji-mini4pro-001",
            config.normalizedSourceId,
        )
    }

    @Test
    fun rejectsCleartextAndApplicationPaths() {
        expectInvalid {
            DjiBridgeRuntimeConfig(
                edgeAiBaseUrl="http://192.168.46.7:8000",
                droneId=1,
                sourceId="dji-test",
            )
        }
        expectInvalid {
            DjiBridgeRuntimeConfig(
                edgeAiBaseUrl=(
                    "https://192.168.46.7:3443/api/ingest/dji"
                ),
                droneId=1,
                sourceId="dji-test",
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
            )
        }
        expectInvalid {
            DjiBridgeRuntimeConfig(
                edgeAiBaseUrl="https://user@host:3443",
                droneId=1,
                sourceId="dji-test",
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
            )
        }
        expectInvalid {
            DjiBridgeRuntimeConfig(
                edgeAiBaseUrl="https://192.168.46.7:3443",
                droneId=1,
                sourceId="  ",
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
