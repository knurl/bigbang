package com.bbclient

import java.text.SimpleDateFormat
import java.util.*

class Logger @JvmOverloads constructor(label: String, header: String = "", footer: String = "", private val addTimestamp: Boolean = false) {
    private val label: String = label.uppercase(Locale.getDefault())
    private val emphasis: Boolean = header.isNotEmpty()
    private var header: String? = null
    private var footer: String? = null
    private val formatter = SimpleDateFormat("HH:mm:ss.SS")

    init {
        if (header.isNotEmpty()) {
            this.header = " $header "

            if (footer.isNotEmpty()) this.footer = " $footer "
            else this.footer = this.header
        } else {
            this.header = ""
            this.footer = ""
        }
    }

    fun log(s: String, plain: Boolean) {
        val current = formatter.format(Calendar.getInstance().time).toString() + ": "
        println((if (addTimestamp) current else "")
                + "[${label}]: $header"
                + (if (emphasis && !plain) s.uppercase(Locale.getDefault()) else s)
                + "$footer")
    }

    fun log(s: String) = log(s, plain = false)
}
