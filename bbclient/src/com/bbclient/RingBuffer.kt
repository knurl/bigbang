package com.bbclient

import kotlinx.coroutines.*

/**
 * RingBuffer uses a fixed length array to implement a queue, where,
 * - [tail] Items are added to the tail
 * - [head] Items are removed from the head
 * - [size] Keeps track of how many items are currently in the queue
 */
@OptIn(ExperimentalCoroutinesApi::class, DelicateCoroutinesApi::class) class RingBuffer<T>(private val capacity: Int = 10) {
    /*
     * We will use a single thread to enforce synchronization of all elements internally,
     * including the contained ArrayList.
     */
    private val confined = newSingleThreadContext("RingBufferContext")
    private val arrayList = ArrayList<T>(capacity)
    private var head = 0 // read index
    private var tail = 0 // write index; points to place where we will write _next_ item
    private var newest = 0 // points to newest item in queue
    private var size = 0 // how many items in queue

    fun getSize() = runBlocking {
        withContext(confined) {
            size
        }
    }
    fun isEmpty() = getSize() == 0

    suspend fun hasCapacity() = withContext(confined) { size < capacity }

    /* Operates at head--oldest end */
    suspend fun dequeue(): T {
        val result: T
        withContext(confined) {
            // Check if queue is empty before attempting to remove the item
            if (size == 0) throw UnderflowException("Queue is empty, can't dequeue()")

            result = arrayList[head]
            // Loop around to the start of the array if there's a need for it
            head = (head + 1) % capacity
            size--
        }

        return result
    }

    /* Operates at tail--newest end */
    suspend fun enqueue(item: T) {
        // Check if there's space before attempting to add the item
        withContext(confined) {
            if (!hasCapacity())
                throw OverflowException("Queue is full, can't enqueue()")

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
        }
    }

    /*
     * This returns the oldest item in the ring buffer.
     */
    suspend fun peekHead(): T {
        val headItem: T
        withContext(confined) {
            // only guaranteed to have an element at head end if queue size nonzero
            if (size < 1)
                throw NoSuchElementException()

            headItem = arrayList[head]
        }
        return headItem
    }

    /*
     * This returns the newest item in the ring buffer
     */
    suspend fun peekTail(): T {
        val tailItem: T
        withContext(confined) {
            // only guaranteed to have an element at tail end if queue size nonzero
            if (size < 1)
                throw NoSuchElementException()

            tailItem = arrayList[newest]
        }
        return tailItem
    }

    suspend fun asList(): List<T> {
        val listCopy = mutableListOf<T>()

        withContext(confined) {
            var itemCount = size
            var readIndex = head

            while (itemCount > 0) {
                listCopy.add(arrayList[readIndex])
                readIndex = (readIndex + 1) % capacity
                itemCount--
            }

            assert(listCopy[0] == arrayList[head])
            assert(listCopy.size == size)
        }

        return listCopy
    }
}

class OverflowException(msg: String) : RuntimeException(msg)
class UnderflowException(msg: String) : RuntimeException(msg)
