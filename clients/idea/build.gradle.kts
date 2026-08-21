plugins {
    id("java")
    id("org.jetbrains.kotlin.jvm") version "1.9.24"
    id("org.jetbrains.intellij") version "1.17.4"
}

group = "com.dashuai"
version = "0.3.0"

repositories {
    mavenCentral()
}

intellij {
    version.set("2023.3.6")
    type.set("IC")
    plugins.set(listOf())
}

tasks {
    patchPluginXml {
        sinceBuild.set("233")
        untilBuild.set("243.*")
    }
}

kotlin {
    jvmToolchain(17)
}
