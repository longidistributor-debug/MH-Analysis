plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "com.mh.analysis"
    compileSdk = 35

    defaultConfig {
        applicationId = "com.mh.analysis"
        minSdk = 26
        targetSdk = 33
        versionCode = 34
        versionName = "V.02"
    }

    val signingStoreFile = System.getenv("MH_SIGNING_STORE_FILE")
    val signingStorePassword = System.getenv("MH_ANDROID_STORE_PASSWORD")
    val signingKeyAlias = System.getenv("MH_ANDROID_KEY_ALIAS")
    val signingKeyPassword = System.getenv("MH_ANDROID_KEY_PASSWORD")
    val hasReleaseSigning = !signingStoreFile.isNullOrBlank() &&
        !signingStorePassword.isNullOrBlank() &&
        !signingKeyAlias.isNullOrBlank() &&
        !signingKeyPassword.isNullOrBlank()

    if (hasReleaseSigning) {
        signingConfigs {
            create("mhRelease") {
                storeFile = file(signingStoreFile!!)
                storePassword = signingStorePassword
                keyAlias = signingKeyAlias
                keyPassword = signingKeyPassword
                enableV1Signing = true
                enableV2Signing = true
                enableV3Signing = true
                enableV4Signing = true
            }
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            if (hasReleaseSigning) {
                signingConfig = signingConfigs.getByName("mhRelease")
            }
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions { jvmTarget = "17" }
}

dependencies {
    implementation("com.squareup.okhttp3:okhttp:4.12.0")
    implementation("androidx.core:core:1.13.1")
}
