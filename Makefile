./tags: ./bigbang.py ./run.py
	/usr/local/bin/ctags -R --languages=python --python-kinds=-i -f $@ $^

clean:
	rm -f tags
