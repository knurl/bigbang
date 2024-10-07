package com.bbclient

import java.time.Instant
import java.util.regex.Pattern
import java.util.regex.PatternSyntaxException

class SocketResponseResponder {
    private val lock = Object()

    private val respFail: String = "BB 400 BADREQUEST"
    private val respOk: String = "BB 200 OK"
    private val respTimeout: String = "BB 408 TIMEOUT"

    /*
     * Synchronized
     */
    private var memberAddress: String? = null
    private var isReadyForChaosStart: Boolean = false

    var chaosStartTime: Instant? = null
        get() = synchronized(lock) { chaosStartTime }
        private set
    private var isReadyForChaosStop: Boolean = false

    var isChaosStopped: Boolean = false
        get() = synchronized(lock) { isChaosStopped }
        private set
    private var testResults: String? = null

    var isTestResultReceived: Boolean = false
        get() = synchronized(lock) { isTestResultReceived }
        private set

    fun resetTest() {
        synchronized(lock) {
            isReadyForChaosStart = false
            chaosStartTime = null
            isReadyForChaosStop = false
            isChaosStopped = false
            testResults = null
            isTestResultReceived = false
        }
    }

    private fun setMemberAddress(memberAddress: String?) {
        synchronized(lock) {
            this.memberAddress = memberAddress
            lock.notifyAll()
        }
    }

    fun awaitMemberAddress(): String {
        synchronized(lock) {
            while (memberAddress == null) {
                try {
                    lock.wait()
                } catch (e: InterruptedException) {
                    throw RuntimeException(e)
                }
            }
            return memberAddress!!
        }
    }

    private val isMemberAddressSet: Boolean
        get() = synchronized(lock) { this.memberAddress != null }

    fun setIsNotReadyForChaosStart() {
        synchronized(lock) {
            this.isReadyForChaosStart = false
        }
    }

    fun setIsReadyForChaosStart() {
        synchronized(lock) {
            this.isReadyForChaosStart = true
            lock.notifyAll()
        }
    }

    private fun awaitIsReadyForChaosStart() {
        synchronized(lock) {
            while (!isReadyForChaosStart) {
                try {
                    lock.wait(2000)
                } catch (e: InterruptedException) {
                    throw RuntimeException(e)
                }
            }
        }
    }

    fun setChaosStartTime() {
        synchronized(lock) {
            this.chaosStartTime = Instant.now()
        }
    }

    fun setIsNotReadyForChaosStop() {
        synchronized(lock) {
            this.isReadyForChaosStop = false
        }
    }

    fun setIsReadyForChaosStop() {
        synchronized(lock) {
            this.isReadyForChaosStop = true
            lock.notifyAll()
        }
    }

    private fun awaitIsReadyForChaosStop() {
        synchronized(lock) {
            while (!isReadyForChaosStop) {
                try {
                    lock.wait(2000)
                } catch (e: InterruptedException) {
                    throw RuntimeException(e)
                }
            }
        }
    }

    fun setIsChaosStopped() {
        synchronized(lock) {
            this.isChaosStopped = true
        }
    }

    fun setTestResult(testResults: String?) {
        synchronized(lock) {
            this.testResults = testResults
            lock.notifyAll()
        }
    }

    private fun awaitTestResult(): String {
        synchronized(lock) {
            while (testResults == null) {
                try {
                    lock.wait(2000)
                } catch (e: InterruptedException) {
                    throw RuntimeException(e)
                }
            }

            return this.testResults!!
        }
    }

    fun setIsTestResultReceived() {
        synchronized(lock) {
            this.isTestResultReceived = true
        }
    }

    fun handleIncomingMessage(protocolMessage: String): String {
        val returnCode: String
        var retVal = ""
        val logger = Logger("Incoming", "==>", "<==")

        val atoms = protocolMessage.split(" ".toRegex()).dropLastWhile { it.isEmpty() }.toTypedArray()
        val verb = atoms[0]

        returnCode = when (verb) {
            "HELLO" -> respOk
            "MADDR" -> {
                if (atoms.size > 1) {
                    val address = atoms[1]
                    if (isValidIp(address)) {
                        if (!isMemberAddressSet) {
                            logger.log("Setting memberAddress to $address")
                            this.setMemberAddress(address)
                            respOk
                        } else {
                            try {
                                Thread.sleep(2000)
                            } catch (e: InterruptedException) {
                                logger.log("*** RECEIVED EXCEPTION [SETMEMBADDR] *** %s".format(e))
                                throw RuntimeException(e)
                            }
                            respTimeout
                        }
                    }
                }

                respFail
            }

            "WLOAD" -> {
                awaitIsReadyForChaosStart()
                logger.log("Stats min pop -> client being told ready to start chaos")
                respOk
            }

            "CHSTR" -> {
                setChaosStartTime()
                logger.log("Client has started chaos")
                respOk
            }

            "WCSTR" -> {
                awaitIsReadyForChaosStop()
                logger.log("Client received signal from driver to stop chaos")
                respOk
            }

            "CHSTP" -> {
                setIsChaosStopped()
                logger.log("Client has stopped chaos")
                respOk
            }

            "WTRES" -> {
                val testResults = awaitTestResult()
                logger.log("Transmit test results")
                retVal = testResults
                respOk
            }

            "ACKTR" -> {
                setIsTestResultReceived()
                logger.log("Test results ack from client")
                respOk
            }

            else -> respFail
        }

        val outputString = StringBuilder(returnCode)
        if (retVal.isNotEmpty()) {
            outputString.append(": ")
            outputString.append(retVal)
            logger.log("Sending back: $outputString")
        }

        return outputString.toString()
    }

    companion object {
        fun isValidIp(testIp: String?): Boolean {
            var ip = testIp
            if (ip.isNullOrEmpty()) return false
            ip = ip.trim { it <= ' ' }
            if ((ip.length < 6) || (ip.length > 15)) return false

            try {
                val pattern =
                    Pattern.compile("^(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$")
                val matcher = pattern.matcher(ip)
                return matcher.matches()
            } catch (ex: PatternSyntaxException) {
                return false
            }
        }
    }
}
