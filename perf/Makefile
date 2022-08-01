PYFILES = $(wildcard *.py)

ALL: mypy ./tags

mypy: $(PYFILES)
	MYPYPATH=.:.. mypy $^

./tags: $(PYFILES)
	/usr/local/bin/ctags --languages=python --python-kinds=-i -f $@ $^

clean:
	rm -f tags
