package com.visionflow.dji.bridge

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import java.nio.charset.StandardCharsets
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

internal class DjiBridgeSecretStore(
    context: Context,
    storageSuffix: String = "",
) {
    private val normalizedStorageSuffix =
        validateStorageSuffix(storageSuffix)
    private val preferencesName =
        PREFERENCES_NAME + normalizedStorageSuffix
    private val keyAlias =
        KEY_ALIAS + normalizedStorageSuffix
    private val preferences =
        context.applicationContext.getSharedPreferences(
            preferencesName,
            Context.MODE_PRIVATE,
        )

    fun save(secret: String) {
        require(secret.length >= MIN_SECRET_LENGTH) {
            "DJI bridge key must be at least $MIN_SECRET_LENGTH characters"
        }
        require(secret.none { it.isWhitespace() }) {
            "DJI bridge key must not contain whitespace"
        }

        val clearBytes = secret.toByteArray(StandardCharsets.UTF_8)
        try {
            val cipher = Cipher.getInstance(TRANSFORMATION)
            cipher.init(
                Cipher.ENCRYPT_MODE,
                getOrCreateSecretKey(),
            )
            val encrypted = cipher.doFinal(clearBytes)

            val committed =
                preferences.edit()
                    .putString(
                        KEY_IV,
                        Base64.encodeToString(
                            cipher.iv,
                            Base64.NO_WRAP,
                        ),
                    )
                    .putString(
                        KEY_CIPHERTEXT,
                        Base64.encodeToString(
                            encrypted,
                            Base64.NO_WRAP,
                        ),
                    )
                    .commit()

            check(committed) {
                "DJI bridge encrypted credential could not be persisted"
            }
        } finally {
            clearBytes.fill(0)
        }
    }

    fun load(): String? {
        val encodedIv =
            preferences.getString(
                KEY_IV,
                null,
            ) ?: return null
        val encodedCiphertext =
            preferences.getString(
                KEY_CIPHERTEXT,
                null,
            ) ?: return null

        try {
            val cipher = Cipher.getInstance(TRANSFORMATION)
            cipher.init(
                Cipher.DECRYPT_MODE,
                getOrCreateSecretKey(),
                GCMParameterSpec(
                    GCM_TAG_LENGTH_BITS,
                    Base64.decode(
                        encodedIv,
                        Base64.NO_WRAP,
                    ),
                ),
            )
            val clearBytes =
                cipher.doFinal(
                    Base64.decode(
                        encodedCiphertext,
                        Base64.NO_WRAP,
                    ),
                )

            return try {
                String(
                    clearBytes,
                    StandardCharsets.UTF_8,
                )
            } finally {
                clearBytes.fill(0)
            }
        } catch (error: Exception) {
            throw IllegalStateException(
                "DJI bridge credential could not be decrypted",
                error,
            )
        }
    }

    fun isConfigured(): Boolean =
        preferences.contains(KEY_IV) &&
            preferences.contains(KEY_CIPHERTEXT)

    fun clear() {
        check(preferences.edit().clear().commit()) {
            "DJI bridge encrypted credential could not be cleared"
        }

        val keyStore =
            KeyStore.getInstance(ANDROID_KEYSTORE).apply {
                load(null)
            }
        if (keyStore.containsAlias(keyAlias)) {
            keyStore.deleteEntry(keyAlias)
        }
    }

    private fun getOrCreateSecretKey(): SecretKey {
        val keyStore =
            KeyStore.getInstance(ANDROID_KEYSTORE).apply {
                load(null)
            }
        val existing =
            keyStore.getKey(
                keyAlias,
                null,
            ) as? SecretKey
        if (existing != null) {
            return existing
        }

        val keyGenerator =
            KeyGenerator.getInstance(
                KeyProperties.KEY_ALGORITHM_AES,
                ANDROID_KEYSTORE,
            )
        keyGenerator.init(
            KeyGenParameterSpec.Builder(
                keyAlias,
                KeyProperties.PURPOSE_ENCRYPT or
                    KeyProperties.PURPOSE_DECRYPT,
            )
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(
                    KeyProperties.ENCRYPTION_PADDING_NONE,
                )
                .setRandomizedEncryptionRequired(true)
                .build(),
        )
        return keyGenerator.generateKey()
    }

    companion object {
        internal fun validateStorageSuffix(value: String): String {
            require(
                value.isEmpty() ||
                    STORAGE_SUFFIX_PATTERN.matches(value)
            ) {
                "storageSuffix must be empty or match " +
                    "_[A-Za-z0-9_-]{1,40}"
            }
            return value
        }

        private const val MIN_SECRET_LENGTH = 32
        private const val PREFERENCES_NAME =
            "visionflow_dji_bridge_secret"
        private const val KEY_IV = "credential_iv"
        private const val KEY_CIPHERTEXT = "credential_ciphertext"
        private const val KEY_ALIAS =
            "visionflow_dji_bridge_runtime_key_v1"
        private const val ANDROID_KEYSTORE = "AndroidKeyStore"
        private const val TRANSFORMATION = "AES/GCM/NoPadding"
        private const val GCM_TAG_LENGTH_BITS = 128
        private val STORAGE_SUFFIX_PATTERN =
            Regex("^_[A-Za-z0-9_-]{1,40}$")
    }
}
