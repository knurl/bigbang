./tags: ./bigbang.py ./run.py
	/usr/local/bin/ctags -R --languages=python --python-kinds=-i -f $@ $^

mypy:
	mypy ./bigbang.py ./run.py

clean:
	rm -f tags
