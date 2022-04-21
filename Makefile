mypy:
	mypy ./bigbang.py ./run.py ./capcalc.py

./tags: ./bigbang.py ./run.py ./capcalc.py
	/usr/local/bin/ctags --languages=python --python-kinds=-i -f $@ $^

clean:
	rm -f tags
