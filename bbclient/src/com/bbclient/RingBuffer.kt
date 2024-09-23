package com.bbclient.com.bbclient

/**
 * RingBuffer uses a fixed length array to implement a queue, where,
 * - [tail] Items are added to the tail
 * - [head] Items are removed from the head
 * - [ringSize] Keeps track of how many items are currently in the queue
 */
class RingBuffer<T>(private val maxSize: Int = 10): ArrayList<T>(maxSize) {
    // Head - remove from the head (read index)
    private var head = 0

    // Tail - add to the tail (write index)
    private var tail = 0

    // How many items are currently in the queue
    var ringSize = 0
        private set

    private fun dequeue(): T {
        // Check if queue is empty before attempting to remove the item
        if (ringSize == 0) throw UnderflowException("Queue is empty, can't dequeue()")

        val result = super.get(head)
        // Loop around to the start of the array if there's a need for it
        head = (head + 1) % maxSize
        ringSize--

        return result
    }

    fun enqueue(item: T): T {
        // Check if there's space before attempting to add the item
        if (ringSize == maxSize)
            dequeue()

        if (super.size <= ringSize)
            super.add(item)
        else
            super.set(tail, item)

        val tailItem = super.get(tail)
        // Loop around to the start of the array if there's a need for it
        tail = (tail + 1) % maxSize
        ringSize++
        return tailItem
    }

    fun peekHead(): T {
        return super.get(head)
    }
}

class UnderflowException(msg: String) : RuntimeException(msg)
