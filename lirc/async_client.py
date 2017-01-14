''' Asynchronous python bindings for the lircd socket interface. '''
##
#   @file async_client.py
#   @author Alec Leamas
#   @brief Asynchronour python bindings for a subset of the lirc_client.h
#   interface.
#   @ingroup  python_bindings

##  @addtogroup python_bindings
#   @{

##
#
#   This module provides asynchronous interfaces to read lirc data
#   on tóp of client.py. The API is unstable.
#
#
#   Reading raw data
#   ----------------
#
#   Reading raw data direct from the lircd socket can be done with the
#   RawConnection object using something like
#
#          import asyncio
#          import lirc.client
#          import lirc.async_client
#
#          async def main(socket_path, loop):
#              conn = lirc.client.RawConnection(socket_path)
#              async with lirc.async_client.AsyncConnection(conn, loop) as c:
#                  async for keypress in c:
#                      print(keypress or "None")
#
#          if __name__ == "__main__":
#              socket_path =  .....
#              loop = asyncio.get_event_loop()
#              loop.run_until_complete(main(socket_path, loop))
#              loop.close()

#   pylint: disable=W0613

import asyncio


class AsyncConnection(object):
    ''' Asynchronous read interface on top of a Connection. '''

    def __init__(self, connection, loop):

        def read_from_fd():
            ''' Read data from the conn fd and put into queue. '''
            line = self._conn.readline(0)
            if line:
                asyncio.ensure_future(self._queue.put(line))

        self._conn = connection
        self._loop = loop
        self._queue = asyncio.Queue(loop=self._loop)
        self._loop.add_reader(self._conn.fileno(), read_from_fd)

    def close(self):
        ''' Clean up loop and the base connection. '''
        self._loop.remove_reader(self._conn.fileno())
        self._conn.close()

    async def readline(self):
        ''' Asynchronous get next line from the connection. '''
        return await self._queue.get()

    def __aiter__(self):
        ''' Return async iterator. '''
        return self

    async def __anext__(self):
        ''' Implement async iterator.next(). '''
        return await self._queue.get()

    async def __aenter__(self):
        ''' Implement enter async context manager. '''
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        ''' Implement exit async context manager. '''
        self.close()
