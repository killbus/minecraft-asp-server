plugins {
    java
}

group = "io.github.killbus"
version = "0.1.0"
description = "Online statistics sidebar using Multiverse-Inventories scopes"

repositories {
    mavenCentral()
    maven("https://repo.papermc.io/repository/maven-public/")
    maven("https://repo.onarandombox.com/multiverse-releases/") {
        content {
            includeGroup("org.mvplugins.multiverse.core")
            includeGroup("org.mvplugins.multiverse.inventories")
        }
    }
    maven("https://repo.codemc.io/repository/maven-releases/") {
        content { includeGroup("com.github.retrooper") }
    }
}

dependencies {
    compileOnly("io.papermc.paper:paper-api:26.2.build.135-stable")
    compileOnly("org.mvplugins.multiverse.core:multiverse-core:5.8.1") {
        isTransitive = false
    }
    compileOnly("org.mvplugins.multiverse.inventories:multiverse-inventories:5.3.6") {
        isTransitive = false
    }
    compileOnly("com.github.retrooper:packetevents-spigot:2.14.0")
}

java {
    toolchain.languageVersion.set(JavaLanguageVersion.of(25))
}

tasks.withType<JavaCompile>().configureEach {
    options.encoding = "UTF-8"
    options.release.set(25)
}

tasks.processResources {
    inputs.property("version", project.version)
    filesMatching("plugin.yml") { expand("version" to project.version) }
}

tasks.withType<AbstractArchiveTask>().configureEach {
    isPreserveFileTimestamps = false
    isReproducibleFileOrder = true
}

tasks.wrapper {
    gradleVersion = "9.7.1"
    distributionType = Wrapper.DistributionType.BIN
    distributionSha256Sum = "acd53f1edaf02f1a8ff99879f8a34b302661a057d9b063ae9e35b552f804d20a"
}
