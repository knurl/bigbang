package com.bbclient;

import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import java.util.Random;

public class RandomStringBuilder {

    public static String generateRandomString(int length) {
        var random = new Random();
        var sb = new StringBuilder();
        final int blockLength = 64;
        final int numBlocks = length / blockLength;
        final int remainder = length % blockLength;
        var array = new byte[blockLength];
        random.nextBytes(array);
        var remainderArray = Arrays.copyOfRange(array, 0, remainder);
        java.lang.String block = new java.lang.String(array, StandardCharsets.US_ASCII);
        java.lang.String remainderBlock = new java.lang.String(remainderArray);
        sb.append(block.repeat(numBlocks));
        sb.append(remainderBlock);
        assert sb.length() == length;
        return sb.toString();
    }
}
