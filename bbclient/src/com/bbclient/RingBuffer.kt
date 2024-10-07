package com.bbclient

/**
 * RingBuffer uses a fixed length array to implement a queue, where,
 * - [tail] Items are added to the tail
 * - [head] Items are removed from the head
 * - [size] Keeps track of how many items are currently in the queue
 */
class RingBuffer<T>(private val capacity: Int = 10): Iterable<T> {
    private val arrayList = ArrayList<T>(capacity)
    private var head = 0 // read index
    private var tail = 0 // write index; points to place where we will write _next_ item
    private var newest = 0 // points to newest item in queue
    var size = 0 // how many items in queue
        private set

    fun isEmpty() = size == 0
    fun isNotEmpty() = !isEmpty()
    fun hasCapacity() = size < capacity

    /* Operates at head--oldest end */
    fun dequeue(): T {
        // Check if queue is empty before attempting to remove the item
        if (size == 0) throw UnderflowException("Queue is empty, can't dequeue()")

        val removed: T = arrayList[head]
        // Loop around to the start of the array if there's a need for it
        head = (head + 1) % capacity
        size--

        return removed
    }

    /* Operates at tail--newest end */
    fun enqueue(item: T) {
        // Check if there's space before attempting to add the item
        var inserted = false

        while (!inserted) {
            if (!hasCapacity())
                throw OverflowException("Queue is full, can't enqueue()")

            if (size < capacity) {
                if (arrayList.size <= size)
                    arrayList.add(item)
                else
                    arrayList[tail] = item

                newest = tail

                /*
                 * Move the tail forward. Note that the tail points, potentially, to an
                 * empty slot ahead of the newest item, as it represents the write point
                 * for the _next_ write. The tail will loop around to the start of the
                 * array if there's a need for it.
                 */
                tail = (tail + 1) % capacity
                size++
                inserted = true
            }
        }
    }

    private fun get(index: Int): T {
        // only guaranteed to have an element at head end if queue size nonzero
        if (size < 1)
            throw NoSuchElementException()

        return arrayList[index]
    }

    /*
     * This returns the newest item in the ring buffer
     */
    fun peekTail() = get(newest)

    inner class RingBufferIterator: Iterator<T> {
        private var readIndex = head
        private var itemCount = size

        override fun hasNext() = itemCount > 0

        override fun next(): T {
            val toReturn = arrayList[readIndex]
            readIndex = (readIndex + 1) % capacity
            itemCount--
            return toReturn
        }

    }

    override fun iterator(): Iterator<T> = RingBufferIterator()
}

class OverflowException(msg: String) : RuntimeException(msg)
class UnderflowException(msg: String) : RuntimeException(msg)
