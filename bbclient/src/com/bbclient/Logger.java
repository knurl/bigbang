package com.bbclient;

import java.time.Instant;
import java.time.format.DateTimeFormatterBuilder;

class Logger {
    static synchronized void log(String s) {
        var formatter = new DateTimeFormatterBuilder().appendInstant(3).toFormatter();
        System.out.println(formatter.format(Instant.now()) + ": " + s);
    }
}
