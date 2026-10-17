plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

// Номер сборки берётся из GitHub Actions, чтобы каждая новая версия ставилась поверх старой.
val buildNumber = (System.getenv("GITHUB_RUN_NUMBER") ?: "1").toInt()
val siteUrl = System.getenv("SITE_URL") ?: "https://nvra.ru"

android {
    namespace = "ru.nvra.app"
    compileSdk = 35

    defaultConfig {
        applicationId = "ru.nvra.app"
        minSdk = 24
        targetSdk = 35
        versionCode = buildNumber
        versionName = "1.0.$buildNumber"
        buildConfigField("String", "SITE_URL", "\"$siteUrl\"")
        buildConfigField("String", "SITE_HOST", "\"${siteUrl.removePrefix("https://").removePrefix("http://").trimEnd('/')}\"")
    }

    buildFeatures {
        buildConfig = true
    }

    signingConfigs {
        create("release") {
            storeFile = file("../nuvora.keystore")
            storePassword = System.getenv("KEYSTORE_PASSWORD")?.takeIf { it.isNotBlank() } ?: "nuvora-android"
            keyAlias = "nuvora"
            keyPassword = System.getenv("KEYSTORE_PASSWORD")?.takeIf { it.isNotBlank() } ?: "nuvora-android"
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            signingConfig = signingConfigs.getByName("release")
        }
        debug {
            signingConfig = signingConfigs.getByName("release")
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions {
        jvmTarget = "17"
    }
    lint {
        abortOnError = false
        checkReleaseBuilds = false
    }
}

dependencies {
    implementation("androidx.core:core-ktx:1.13.1")
    implementation("androidx.appcompat:appcompat:1.7.0")
    implementation("androidx.activity:activity-ktx:1.9.3")
    implementation("androidx.work:work-runtime-ktx:2.9.1")
}
