plugins {
    id("com.android.application")
    id("org.jetbrains.android")
}

android {
    namespace = "com.mh.analysis"
    compileSdk = 35

    defaultConfig {
        applicationId = "com.mh.analysis"
        minSdk = 26
        targetSdk = 33
        versionCode = 18
        versionName = "18.0"
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
