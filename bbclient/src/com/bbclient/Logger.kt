package com.bbclient

import java.text.SimpleDateFormat
import java.util.*

internal class Logger @JvmOverloads constructor(label: String, header: String = "", footer: String = "", private val addTimestamp: Boolean = false) {
    private val label: String = label.uppercase(Locale.getDefault())
    private var emphasis: Boolean = false
    private var header: String? = null
    private var footer: String? = null
    private val formatter = SimpleDateFormat("HH:mm:ss.SS")

    init {
        if (header.isNotEmpty()) {
            this.emphasis = true
            this.header = " $header "

            if (footer.isNotEmpty()) this.footer = " $footer "
            else this.footer = this.header
        } else {
            this.emphasis = false
            this.header = ""
            this.footer = ""
        }
    }

    fun log(s: String) {
        val current = formatter.format(Calendar.getInstance().time).toString() + ": "
        println((if (addTimestamp) current else "")
                + "[${label}]: $header"
                + (if (emphasis) s.uppercase(Locale.getDefault()) else s)
                + "$footer")
    }
}
