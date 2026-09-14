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
        versionCode = 4
        versionName = "4.0"
    }

    buildTypes {
        release { isMinifyEnabled = false }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions { jvmTarget = "17" }
}
