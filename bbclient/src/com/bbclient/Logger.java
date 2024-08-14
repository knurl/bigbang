package com.bbclient;

class Logger {
    final String header;

    Logger(String header) {
        this.header = header.toUpperCase();
    }

    synchronized void log(String s) {
        System.out.println("[" + this.header + "]: " + s);
    }
}
