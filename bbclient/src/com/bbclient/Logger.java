package com.bbclient;

class Logger {
    final String label;
    final boolean emphasis;
    final String header;
    final String footer;

    Logger(String label, String header, String footer) {
        this.label = label.toUpperCase();

        if (!header.isEmpty()) {
            this.emphasis = true;
            this.header = " " + header + " ";

            if (!footer.isEmpty())
                this.footer = " " + footer + " ";
            else
                this.footer = this.header;
        } else {
            this.emphasis = false;
            this.header = "";
            this.footer = "";
        }
    }

    Logger(String label, String header) {
        this(label, header, header);
    }

    Logger(String label) {
        this(label, "", "");
    }

    void log(String s) {
        synchronized (System.out) {
            System.out.printf("[%s]: %s%s%s%n", label, header, emphasis? s.toUpperCase() : s, footer);
        }
    }
}
