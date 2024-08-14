package com.bbclient;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStreamReader;
import java.io.PrintWriter;
import java.net.ServerSocket;

public class SocketListenerThread extends Thread {
    private final SocketResponseResponder socketResponseResponder;
    private final int portNumber;
    private final Logger logger;

    public SocketListenerThread(SocketResponseResponder socketResponseResponder, int portNumber) {
        this.socketResponseResponder = socketResponseResponder;
        this.portNumber = portNumber;
        this.logger = new Logger("SockListen");
    }

    public void run() {
        try (final var serverSocket = new ServerSocket(portNumber)) {
            while (true) {
                try (final var clientSocket = serverSocket.accept();
                     final var out = new PrintWriter(clientSocket.getOutputStream());
                     final var in = new BufferedReader(new InputStreamReader(clientSocket.getInputStream()))) {
                    final var inputLine = in.readLine();
                    if (inputLine != null) {
                        var outputLine = socketResponseResponder.handleIncomingMessage(inputLine);
                        out.println(outputLine);
                        out.flush();
                    }
                }
            }
        } catch (IOException e) {
            logger.log("*** RECEIVED EXCEPTION [SOCKLISTEN2] *** %s"
                    .formatted(e.getClass().getSimpleName()));
            throw new RuntimeException(e);
        }
    }
}
