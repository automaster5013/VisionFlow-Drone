package com.visionflow.dji.bridge

import org.junit.Assert.assertArrayEquals
import org.junit.Assert.fail
import org.junit.Test

class DjiEncodedStreamUploaderTest {
    @Test
    fun copiesOnlyTheCallbackByteRange() {
        val packet = DjiEncodedStreamUploader.copyPacket(
            data=byteArrayOf(0x11, 0x22, 0x33, 0x44, 0x55),
            offset=1,
            length=3,
        )
        assertArrayEquals(byteArrayOf(0x22, 0x33, 0x44), packet)
    }

    @Test
    fun rejectsInvalidCallbackByteRanges() {
        expectInvalid {
            DjiEncodedStreamUploader.copyPacket(
                data=byteArrayOf(1, 2, 3), offset=-1, length=1,
            )
        }
        expectInvalid {
            DjiEncodedStreamUploader.copyPacket(
                data=byteArrayOf(1, 2, 3), offset=2, length=2,
            )
        }
    }

    private fun expectInvalid(block: () -> Unit) {
        try {
            block()
            fail("Expected IllegalArgumentException")
        } catch (_: IllegalArgumentException) {
            // Expected.
        }
    }
}
