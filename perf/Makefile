PYFILES = $(wildcard *.py ../*.py)

ALL: mypy ./tags

mypy: $(PYFILES)
	MYPYPATH=.:.. mypy --check-untyped-defs $^

./tags: $(PYFILES)
	ctags --languages=python --python-kinds=-i -f $@ $^

clean:
	rm -f tags
