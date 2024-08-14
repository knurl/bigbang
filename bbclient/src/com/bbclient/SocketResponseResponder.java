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
    boolean isReadyForTesting = false;
    boolean isTestingComplete = false;
    String testResults = null;
    private Instant chaosStartTime = null;

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

    public synchronized void setIsReadyForTesting() {
        this.isReadyForTesting = true;
        this.notifyAll();
    }

    private synchronized boolean awaitIsReadyForTesting() {
        if (isReadyForTesting)
            return true;
        try {
            this.wait(2000);
        } catch (InterruptedException e) {
            throw new RuntimeException(e);
        }
        return isReadyForTesting;
    }

    public synchronized void setIsTestingComplete(String testResults) {
        this.isTestingComplete = true;
        this.testResults = testResults;
        this.notifyAll();
    }

    private synchronized boolean awaitIsTestingComplete() {
        if (isTestingComplete)
            return true;
        try {
            this.wait(2000);
        } catch (InterruptedException e) {
            throw new RuntimeException(e);
        }
        return isTestingComplete;
    }

    private synchronized String getTestResults() {
        return this.testResults;
    }

    public synchronized void setChaosStartTime() {
        this.chaosStartTime = Instant.now();
    }

    public synchronized Instant getChaosStartTime() {
        return this.chaosStartTime;
    }

    private void bbLog(String msg) {
        logger.log(msg);
    }

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
        String returnCode = respFail;
        String retVal = "";

        var atoms = protocolMessage.split(" ");
        String verb = atoms[0];

        if (atoms.length == 1) {
            returnCode = switch (verb) {
                case "HELO" -> {
                    retVal = "HELLO TO YOU";
                    yield respOk;
                }
                case "TEST" -> {
                    var isReady = awaitIsReadyForTesting();
                    if (isReady) {
                        yield respOk;
                    } else {
                        yield respTimeout;
                    }
                }
                case "WTST" -> {
                    var isComplete = awaitIsTestingComplete();
                    if (isComplete) {
                        retVal = getTestResults();
                        yield respOk;
                    } else {
                        yield respTimeout;
                    }
                }
                case "STRT" -> {
                    setChaosStartTime();
                    bbLog("*** CHAOS START ***");
                    yield respOk;
                }
                case "STOP" -> {
                    bbLog("*** CHAOS STOP ***");
                    yield respOk;
                }
                default -> respFail;
            };
        } else if (atoms.length == 2) {
            String object = atoms[1];
            returnCode = respFail;

            if (verb.equals("ADDR") && !isMemberAddressSet() && isValidIp(object)) {
                bbLog("Setting memberAddress to " + object);
                this.setMemberAddress(object);
                returnCode = respOk;
            }
        }

        var outputString = new StringBuilder(returnCode);
        if (!retVal.isEmpty()) {
            outputString.append(": ");
            outputString.append(retVal);
            logger.log("Sending back: " + outputString);
        }

        return outputString.toString();
    }
}
