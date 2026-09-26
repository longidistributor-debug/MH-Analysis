package com.mh.analysis

import android.app.Activity
import android.app.AlertDialog
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.provider.Settings
import android.widget.Toast
import androidx.core.content.FileProvider
import okhttp3.OkHttpClient
import okhttp3.Request
import org.json.JSONObject
import java.io.File
import java.security.MessageDigest
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicBoolean

object AppUpdater {
    private const val CHANNEL_MANIFEST = "https://raw.githubusercontent.com/longidistributor-debug/MH-Analysis/android-update-channel/update.json"
    private const val PREFS = "mh_updater"
    private const val PENDING_APK = "pending_apk"
    private const val PENDING_VERSION = "pending_version"
    private const val CHECK_EVERY_MS = 15L * 60L * 1000L

    private val checking = AtomicBoolean(false)
    private val downloading = AtomicBoolean(false)
    @Volatile private var dialogVisible = false
    @Volatile private var lastCheckAt = 0L

    private val http = OkHttpClient.Builder()
        .connectTimeout(6, TimeUnit.SECONDS)
        .readTimeout(20, TimeUnit.SECONDS)
        .followRedirects(true)
        .followSslRedirects(true)
        .build()

    data class UpdateInfo(
        val version: String,
        val versionCode: Long,
        val mandatory: Boolean,
        val downloadUrl: String,
        val sha256: String,
        val notes: String
    )

    fun onActivityResumed(activity: Activity) {
        if (tryInstallPending(activity)) return
        val now = System.currentTimeMillis()
        if (now - lastCheckAt < CHECK_EVERY_MS) return
        lastCheckAt = now
        check(activity)
    }

    fun check(activity: Activity, force: Boolean = false) {
        if (!force && checking.get()) return
        if (!checking.compareAndSet(false, true)) return
        Thread {
            try {
                val req = Request.Builder()
                    .url(CHANNEL_MANIFEST)
                    .header("Cache-Control", "no-cache")
                    .header("User-Agent", "MH-Analysis-Android-Updater/V.01")
                    .build()
                http.newCall(req).execute().use { res ->
                    if (!res.isSuccessful) return@use
                    val body = res.body?.string().orEmpty()
                    if (body.isBlank()) return@use
                    val j = JSONObject(body)
                    val info = UpdateInfo(
                        version = j.optString("version").trim(),
                        versionCode = j.optLong("version_code", 0L),
                        mandatory = j.optBoolean("mandatory", false),
                        downloadUrl = j.optString("download_url").trim(),
                        sha256 = j.optString("sha256").trim().lowercase(),
                        notes = j.optString("notes", "MH Analysis update available").trim()
                    )
                    val current = currentVersionCode(activity)
                    if (info.versionCode > current && info.downloadUrl.startsWith("https://")) {
                        activity.runOnUiThread { showUpdateDialog(activity, info) }
                    }
                }
            } catch (_: Exception) {
                // Update checks never interrupt market analysis.
            } finally {
                checking.set(false)
            }
        }.start()
    }

    @Suppress("DEPRECATION")
    private fun currentVersionCode(activity: Activity): Long {
        val p = activity.packageManager.getPackageInfo(activity.packageName, 0)
        return if (Build.VERSION.SDK_INT >= 28) p.longVersionCode else p.versionCode.toLong()
    }

    private fun showUpdateDialog(activity: Activity, info: UpdateInfo) {
        if (activity.isFinishing || activity.isDestroyed || dialogVisible) return
        dialogVisible = true
        val currentName = runCatching {
            activity.packageManager.getPackageInfo(activity.packageName, 0).versionName ?: "V.01"
        }.getOrDefault("V.01")
        val msg = buildString {
            append("Current: $currentName\n")
            append("Available: ${info.version}\n\n")
            if (info.notes.isNotBlank()) append(info.notes)
        }
        val b = AlertDialog.Builder(activity)
            .setTitle("MH Analysis Update Available")
            .setMessage(msg)
            .setPositiveButton("UPDATE NOW") { _, _ ->
                dialogVisible = false
                downloadAndInstall(activity, info)
            }
            .setOnDismissListener { dialogVisible = false }
        if (!info.mandatory) {
            b.setNegativeButton("LATER") { d, _ -> d.dismiss() }
        } else {
            b.setCancelable(false)
        }
        b.show()
    }

    private fun downloadAndInstall(activity: Activity, info: UpdateInfo) {
        if (!downloading.compareAndSet(false, true)) return
        Toast.makeText(activity, "Downloading ${info.version} update…", Toast.LENGTH_SHORT).show()
        Thread {
            var target: File? = null
            try {
                val dir = File(activity.cacheDir, "updates").apply { mkdirs() }
                target = File(dir, "MH-Analysis-${info.version}.apk")
                val req = Request.Builder().url(info.downloadUrl).header("User-Agent", "MH-Analysis-Android-Updater/V.01").build()
                http.newCall(req).execute().use { res ->
                    if (!res.isSuccessful) throw IllegalStateException("HTTP ${res.code}")
                    val body = res.body ?: throw IllegalStateException("empty update")
                    target.outputStream().use { out -> body.byteStream().use { input -> input.copyTo(out) } }
                }
                if (info.sha256.isNotBlank()) {
                    val actual = sha256(target)
                    if (!actual.equals(info.sha256, true)) {
                        target.delete()
                        throw IllegalStateException("update verification failed")
                    }
                }
                val prefs = activity.getSharedPreferences(PREFS, Activity.MODE_PRIVATE)
                prefs.edit().putString(PENDING_APK, target.absolutePath).putString(PENDING_VERSION, info.version).apply()
                activity.runOnUiThread { launchInstallerOrPermission(activity, target) }
            } catch (e: Exception) {
                target?.delete()
                activity.runOnUiThread { Toast.makeText(activity, "Update download failed: ${e.message}", Toast.LENGTH_LONG).show() }
            } finally {
                downloading.set(false)
            }
        }.start()
    }

    private fun tryInstallPending(activity: Activity): Boolean {
        val prefs = activity.getSharedPreferences(PREFS, Activity.MODE_PRIVATE)
        val path = prefs.getString(PENDING_APK, null) ?: return false
        val file = File(path)
        if (!file.exists()) {
            clearPending(activity)
            return false
        }
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O && !activity.packageManager.canRequestPackageInstalls()) return false
        launchInstaller(activity, file)
        return true
    }

    private fun launchInstallerOrPermission(activity: Activity, apk: File) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O && !activity.packageManager.canRequestPackageInstalls()) {
            Toast.makeText(activity, "Allow MH Analysis to install updates, then return to the app.", Toast.LENGTH_LONG).show()
            val i = Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES, Uri.parse("package:${activity.packageName}"))
            activity.startActivity(i)
            return
        }
        launchInstaller(activity, apk)
    }

    private fun launchInstaller(activity: Activity, apk: File) {
        try {
            val uri = FileProvider.getUriForFile(activity, "${activity.packageName}.updates", apk)
            clearPending(activity)
            val i = Intent(Intent.ACTION_VIEW).apply {
                setDataAndType(uri, "application/vnd.android.package-archive")
                addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
                addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            }
            activity.startActivity(i)
        } catch (e: Exception) {
            Toast.makeText(activity, "Unable to open Android installer: ${e.message}", Toast.LENGTH_LONG).show()
        }
    }

    private fun clearPending(activity: Activity) {
        activity.getSharedPreferences(PREFS, Activity.MODE_PRIVATE).edit()
            .remove(PENDING_APK)
            .remove(PENDING_VERSION)
            .apply()
    }

    private fun sha256(file: File): String {
        val md = MessageDigest.getInstance("SHA-256")
        file.inputStream().use { input ->
            val buffer = ByteArray(8192)
            while (true) {
                val n = input.read(buffer)
                if (n <= 0) break
                md.update(buffer, 0, n)
            }
        }
        return md.digest().joinToString("") { "%02x".format(it) }
    }
}
