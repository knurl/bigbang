./tags: ./bigbang.py ./run.py ./capcalc.py
	/usr/local/bin/ctags -R --languages=python --python-kinds=-i -f $@ $^

mypy:
	mypy ./bigbang.py ./run.py ./capcalc.py

clean:
	rm -f tags
