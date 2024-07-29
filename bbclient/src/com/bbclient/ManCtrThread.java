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
    private boolean isReady = false;
    private long heapCost;
    private boolean isClusterSafe;
    private int partitionMigrationQ;
    private int numMembers;

    private synchronized void setIsReady(boolean isReady) {
        this.isReady = isReady;
    }

    private synchronized boolean notReady() {
        return !this.isReady;
    }

    public synchronized long getHeapCost() throws NotReadyException {
        if (notReady())
            throw new NotReadyException();
        return heapCost;
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

    private synchronized void setClusterState(boolean isClusterSafe,
                                              int partitionMigrationQ,
                                              int numMembers) {
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
        con = (HttpURLConnection)url.openConnection();
        int responseCode = con.getResponseCode();
        if (responseCode != HttpURLConnection.HTTP_OK) {
            throw new HttpRetryException("Failed to connect to URL " + url,
                    responseCode);
        }

        StringBuilder response;
        try (BufferedReader in = new BufferedReader(new InputStreamReader(con.getInputStream()))) {
            String inputLine;
            response = new StringBuilder();

            while ((inputLine = in.readLine()) != null) {
                response.append(inputLine);
            }
        }

        // read the json strings and convert it into JsonNode
        return (new ObjectMapper()).readTree(response.toString());
    }

    void updateFromRest() {
        JsonNode jsonNodeMap;
        JsonNode jsonNodeCluster;
        long heapCost;
        boolean safe;
        int qSize;
        int members;
        try {
            jsonNodeMap = getJsonFromRestCall(mapUrl);
            jsonNodeCluster = getJsonFromRestCall(clusterUrl);
        } catch (IOException e) {
            setIsReady(false);
            return;
        }

        heapCost = jsonNodeMap.get("heapCost").asLong();
        safe = jsonNodeCluster.get("safe").asBoolean();
        qSize = jsonNodeCluster.get("partitionMigrationQueueSize").asInt();
        members = jsonNodeCluster.get("members").asInt();
        setMapState(heapCost);
        setClusterState(safe, qSize, members);
        setIsReady(true);
    }

    public void run() {
        final var pollFrequency = 1000;

        while (true) {
            updateFromRest();
            try {
                sleep(pollFrequency);
            } catch (InterruptedException ex) {
                throw new RuntimeException(ex);
            }
        }
    }
}
