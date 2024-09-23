package com.bbclient;

import java.time.Instant;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import java.util.regex.PatternSyntaxException;

public class SocketResponseResponder {
    private final Logger logger = new Logger("SockListen");
    final String respFail = "BB 400 BADREQUEST";
    final String respOk = "BB 200 OK";
    final String respTimeout = "BB 408 TIMEOUT";

    /*
     * Synchronized
     */
    private String memberAddress = null;
    boolean isReadyForChaosStart = false;
    private Instant chaosStartTime = null;
    boolean isReadyForChaosStop = false;
    private boolean isChaosStopped = false;
    String testResults = null;
    private boolean isTestResultReceived = false;

    public synchronized void resetTest() {
        isReadyForChaosStart = false;
        chaosStartTime = null;
        isReadyForChaosStop = false;
        isChaosStopped = false;
        testResults = null;
        isTestResultReceived = false;
    }

    public synchronized void setMemberAddress(String memberAddress) {
        this.memberAddress = memberAddress;
        this.notifyAll();
    }

    public synchronized String awaitMemberAddress() {
        while (memberAddress == null) {
            try {
                this.wait();
            } catch (InterruptedException e) {
                throw new RuntimeException(e);
            }
        }
        return memberAddress;
    }

    public synchronized boolean isMemberAddressSet() {
        return this.memberAddress != null;
    }

    public synchronized void setIsNotReadyForChaosStart() {
        this.isReadyForChaosStart = false;
    }

    public synchronized void setIsReadyForChaosStart() {
        this.isReadyForChaosStart = true;
        this.notifyAll();
    }

    private synchronized boolean awaitIsReadyForChaosStart() {
        try {
            this.wait(2000);
        } catch (InterruptedException e) {
            throw new RuntimeException(e);
        }

        return isReadyForChaosStart;
    }

    public synchronized void setChaosStartTime() {
        this.chaosStartTime = Instant.now();
    }

    public synchronized Instant getChaosStartTime() {
        return this.chaosStartTime;
    }

    public synchronized void setIsNotReadyForChaosStop() {
        this.isReadyForChaosStop = false;
    }

    public synchronized void setIsReadyForChaosStop() {
        this.isReadyForChaosStop = true;
        this.notifyAll();
    }

    private synchronized boolean awaitIsReadyForChaosStop() {
        try {
            this.wait(2000);
        } catch (InterruptedException e) {
            throw new RuntimeException(e);
        }

        return isReadyForChaosStop;
    }

    public synchronized void setIsChaosStopped() {
        this.isChaosStopped = true;
    }

    public synchronized boolean getIsChaosStopped() {
        return this.isChaosStopped;
    }

    public synchronized void setTestResult(String testResults) {
        this.testResults = testResults;
        this.notifyAll();
    }

    private synchronized String awaitTestResult() {
        try {
            this.wait(2000);
        } catch (InterruptedException e) {
            throw new RuntimeException(e);
        }

        return this.testResults;
    }

    public synchronized void setIsTestResultReceived() {
        this.isTestResultReceived = true;
    }

    public synchronized boolean getIsTestResultReceived() {
        return this.isTestResultReceived;
    }

    /*
     * End synchronized
     */

    public static boolean isValidIp(String testIp) {
        var ip = testIp;
        if (ip == null || ip.isEmpty()) return false;
        ip = ip.trim();
        if ((ip.length() < 6) || (ip.length() > 15))
            return false;

        try {
            Pattern pattern = Pattern.compile("^(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$");
            Matcher matcher = pattern.matcher(ip);
            return matcher.matches();
        } catch (PatternSyntaxException ex) {
            return false;
        }
    }

    public String handleIncomingMessage(String protocolMessage) {
        String returnCode;
        String retVal = "";
        var logger = new Logger("Incoming", "==>", "<==");

        var atoms = protocolMessage.split(" ");
        String verb = atoms[0];

        returnCode = switch (verb) {
            case "HELLO" -> respOk;
            case "MADDR" -> {
                if (atoms.length > 1) {
                    var address = atoms[1];
                    if (isValidIp(address)) {
                        if (!isMemberAddressSet()) {
                            logger.log("Setting memberAddress to " + address);
                            this.setMemberAddress(address);
                            yield respOk;
                        } else {
                            try {
                                Thread.sleep(2000);
                            } catch (InterruptedException e) {
                                logger.log("*** RECEIVED EXCEPTION [SETMEMBADDR] *** %s".formatted(e));
                                throw new RuntimeException(e);
                            }
                            yield respTimeout;
                        }
                    }
                }

                yield respFail;
            }
            case "WLOAD" -> {
                if (awaitIsReadyForChaosStart()) {
                    logger.log("Stats min pop -> client being told ready to start chaos");
                    yield respOk;
                } else {
                    yield respTimeout;
                }
            }
            case "CHSTR" -> {
                setChaosStartTime();
                logger.log("Client has started chaos");
                yield respOk;
            }
            case "WCSTR" -> {
                if (awaitIsReadyForChaosStop()) {
                    logger.log("Client received signal from driver to stop chaos");
                    yield respOk;
                } else {
                    yield respTimeout;
                }
            }
            case "CHSTP" -> {
                setIsChaosStopped();
                logger.log("Client has stopped chaos");
                yield respOk;
            }
            case "WTRES" -> {
                String testResults;
                if ((testResults = awaitTestResult()) != null) {
                    logger.log("Transmit test results");
                    retVal = testResults;
                    yield respOk;
                } else {
                    yield respTimeout;
                }
            }
            case "ACKTR" -> {
                setIsTestResultReceived();
                logger.log("Test results ack from client");
                yield respOk;
            }
            default -> respFail;
        };

        var outputString = new StringBuilder(returnCode);
        if (!retVal.isEmpty()) {
            outputString.append(": ");
            outputString.append(retVal);
            logger.log("Sending back: " + outputString);
        }

        return outputString.toString();
    }
}
