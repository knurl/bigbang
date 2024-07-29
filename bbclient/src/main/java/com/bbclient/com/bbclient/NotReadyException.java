package com.bbclient;

public class NotReadyException extends Exception {
    public NotReadyException() {
        super("Have not updated data yet.");
    }
}
