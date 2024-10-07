package com.bbclient

import java.io.BufferedReader
import java.io.IOException
import java.io.InputStreamReader
import java.io.PrintWriter
import java.net.ServerSocket

class SocketListenerThread(private val socketResponseResponder: SocketResponseResponder, private val portNumber: Int) :
    Thread() {
    private val logger = Logger("SockListen")

    override fun run() {
        try {
            ServerSocket(portNumber).use { serverSocket ->
                while (true) {
                    serverSocket.accept().use { clientSocket ->
                        PrintWriter(clientSocket.getOutputStream()).use { out ->
                            BufferedReader(
                                InputStreamReader(clientSocket.getInputStream())
                            ).use { `in` ->
                                val inputLine = `in`.readLine()
                                if (inputLine != null) {
                                    val outputLine = socketResponseResponder.handleIncomingMessage(inputLine)
                                    out.println(outputLine)
                                    out.flush()
                                }
                            }
                        }
                    }
                }
            }
        } catch (e: IOException) {
            logger.log(
                "*** RECEIVED EXCEPTION [SOCKLISTEN2] *** %s".format(e.javaClass.simpleName)
            )
            throw RuntimeException(e)
        }
    }
}
