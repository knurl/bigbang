package com.bbclient

import kotlinx.coroutines.Job
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock

/**
 * RingBuffer uses a fixed length array to implement a queue, where,
 * - [tail] Items are added to the tail
 * - [head] Items are removed from the head
 * - [size] Keeps track of how many items are currently in the queue
 */
class RingBuffer<T>(
    private val capacity: Int = 10,
    private val dequeueCallback: (suspend (T) -> Job)? = null
): Iterable<T> {
    /*
     * We will use a mutex to enforce synchronization of all elements internally.
     */
    private val mutex = Mutex()
    private val arrayList = ArrayList<T>(capacity)
    private var head = 0 // read index
    private var tail = 0 // write index; points to place where we will write _next_ item
    private var newest = 0 // points to newest item in queue
    private var size = 0 // how many items in queue

    suspend fun getSize() = mutex.withLock { size }
    suspend fun isEmpty() = getSize() == 0
    suspend fun isNotEmpty() = !isEmpty()
    suspend fun hasCapacity() = mutex.withLock { size < capacity }

    /* Operates at head--oldest end */
    suspend fun dequeue(): T {
        val removed: T
        mutex.withLock {
            // Check if queue is empty before attempting to remove the item
            if (size == 0) throw UnderflowException("Queue is empty, can't dequeue()")

            removed = arrayList[head]
            // Loop around to the start of the array if there's a need for it
            head = (head + 1) % capacity
            size--
        }

        dequeueCallback?.invoke(removed)
        return removed
    }

    /* Operates at tail--newest end */
    suspend fun enqueue(item: T) {
        // Check if there's space before attempting to add the item
        var inserted = false

        while (!inserted) {
            if (!hasCapacity())
                dequeue() // call with mutex NOT held

            mutex.withLock {
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
    }

    /*
     * This returns the oldest item in the ring buffer.
     */
    suspend fun peekHead(): T = mutex.withLock {
        // only guaranteed to have an element at head end if queue size nonzero
        if (size < 1)
            throw NoSuchElementException()

        arrayList[head]
    }

    /*
     * This returns the newest item in the ring buffer
     */
    suspend fun peekTail(): T = mutex.withLock{
        // only guaranteed to have an element at tail end if queue size nonzero
        if (size < 1)
            throw NoSuchElementException()

        arrayList[newest]
    }

    override fun iterator() = arrayList.listIterator()
}

class UnderflowException(msg: String) : RuntimeException(msg)
