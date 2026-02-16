opus_encode.so: opus_encode.c
	gcc opus_encode.c -O3 -lopus -Wall -Wextra -Wshadow -Wno-unused-result -fPIC -shared -o opus_encode.so

test: opus_encode.c
	gcc opus_encode.c -O3 -lopus -Wall -Wextra -Wshadow -Wno-unused-result -o test

test_debug: opus_encode.c
	gcc opus_encode.c -Og -g -lopus -Wall -Wextra -Wshadow -Wno-unused-result -o test_debug
