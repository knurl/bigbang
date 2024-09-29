package com.bbclient

class RunnablesList : ArrayList<IMapMethodRunnable>() {
    fun listRunnablesToStatsString() =
        this.joinToString(separator = "; ") { it.toStatsString() }

    fun listRunnablesToCSV() =
        this.joinToString(separator = ",") { it.toCSV() }
}
