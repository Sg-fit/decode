#Decoder: A webpage for DECODING and ENCODING with standard CS encoding methods

The quick link is here [https://decode-production-5927.up.railway.app/](https://decode-production-5927.up.railway.app/)

The decoder webpage is a **webtool** that allow users to decode or encode messages with the following encoding formats: Binary, 
Base-64, Hex, etc. It is useful for temporarily checking any readable meaning of a computer message. 

The webpage allows users to **login** and stores their previous **decode/encode history** for convenience. Once user input a message, the program 
check for its readability, by using weighted estimation of the message content. Then users can select **enc/dec blocks** in the pipeline
section, enabling them to manipulate the message in both directions. There is also an **auto detection button**, which use all of the 
enc/dec methods and evaluate the result one by one, outputting the result with the highest readability using the same evaluation method. 
The output will be provided by running the initial message through all of the enc/dec blocks selected by the user. 
The enc and dec methods are prestored in the algorithm, and the block activate them. 

For keeping the history across different sessions, we made a SQLite database. Every time the user select save button on the webpage,
the input, output and the blocks (pipeline section) is stored as a dict into our database. Other times, the pipeline changes will be 
stored in history. However, for the convenience, the database will only keep track of maximum 50 changes. The database is manipulated
using built in methods and other self-declared methods. 

A small malfunction or inconvenience for the code is that the change in the enc/dec block (i.e. change selection of encoding or decoding)
will only apply when the page is "reload" somehow (i.e. change in output triggering refresh). Without other changing any other part
of the website, it is not likely that the modifying of blocks' affect will actually apply. 

**Citation**: 
Other tools used: Json, Pathlib, base64, re 
Source: [Anthgear](https://www.authgear.com/post/base64-encode-decode-guide/), [Ceasar Cipher](https://caesarcipher.org/converters/url-encoder-decoder)
