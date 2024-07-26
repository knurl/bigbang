package com.bbclient;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStreamReader;
import java.net.*;

public class ManCtrThread extends Thread {
    // set by constructor
    private final URL clusterUrl;
    private final URL mapUrl;

    // synchronized
    private boolean ready = false;
    private long heapCost;
    private String clusterState;
    private boolean isClusterSafe;
    private int partitionMigrationQ;
    private int numMembers;

    public static class NotReadyException extends RuntimeException {
        public NotReadyException() {
            super("Have not updated data yet.");
        }
    }

    private synchronized void setIsReady() {
        this.ready = true;
    }

    private synchronized boolean notReady() {
        return !this.ready;
    }

    public synchronized long getHeapCost() throws NotReadyException {
        if (notReady())
            throw new NotReadyException();
        return heapCost;
    }

    public synchronized String getClusterState() throws NotReadyException {
        if (notReady())
            throw new NotReadyException();
        return clusterState;
    }

    public synchronized boolean getIsClusterSafe() throws NotReadyException {
        if (notReady())
            throw new NotReadyException();
        return isClusterSafe;
    }

    public synchronized int getPartitionMigrationQ () throws NotReadyException {
        if (notReady())
            throw new NotReadyException();
        return partitionMigrationQ;
    }

    public synchronized int getNumMembers () throws NotReadyException {
        if (notReady())
            throw new NotReadyException();
        return numMembers;
    }

    private synchronized void setMapState(long heapCost) {
        this.heapCost = heapCost;
    }

    private synchronized void setClusterState(String clusterState,
                                                 boolean isClusterSafe,
                                                 int partitionMigrationQ,
                                                 int numMembers) {
        this.clusterState = clusterState;
        this.isClusterSafe = isClusterSafe;
        this.partitionMigrationQ = partitionMigrationQ;
        this.numMembers = numMembers;
    }

    public ManCtrThread(String dnsSearchDomain,
                        String clusterName,
                        String mapName) throws URISyntaxException, MalformedURLException {
        final String manCtrLoadBalancerName = "manctr" + dnsSearchDomain;
        var manCtrBaseUrl =
                "http://%s:8080/rest".formatted(manCtrLoadBalancerName);
        clusterUrl = new URI(manCtrBaseUrl + "/clusters/" + clusterName).toURL();
        mapUrl = new URI(clusterUrl + "/maps/" + mapName).toURL();
    }

    private JsonNode getJsonFromRestCall(URL url) throws IOException {
        HttpURLConnection con;
        int responseCode;
        con = (HttpURLConnection)url.openConnection();
        responseCode = con.getResponseCode();
        if (responseCode != HttpURLConnection.HTTP_OK)
            throw new IOException();

        StringBuilder response;
        try (BufferedReader in = new BufferedReader(new InputStreamReader(con.getInputStream()))) {
            String inputLine;
            response = new StringBuilder();

            while ((inputLine = in.readLine()) != null)
                response.append(inputLine);
        }

        // read the json strings and convert it into JsonNode
        return (new ObjectMapper()).readTree(response.toString());
    }

    void updateFromRest() throws IOException {
        var jsonNode = getJsonFromRestCall(mapUrl);
        setMapState(jsonNode.get("heapCost").asLong());
        jsonNode = getJsonFromRestCall(clusterUrl);
        setClusterState(
                jsonNode.get("state").asText(),
                jsonNode.get("safe").asBoolean(),
                jsonNode.get("partitionMigrationQueueSize").asInt(),
                jsonNode.get("members").asInt());
        setIsReady();
    }

    public void run() {
        final int minimumPollFrequency = 2_000; // ms

        while (true) {
            try {
                updateFromRest();
            } catch (IOException e) {
                try {
                    sleep(minimumPollFrequency);
                } catch (InterruptedException ex) {
                    throw new RuntimeException(ex);
                }
            }
        }
    }
}
