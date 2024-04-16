PYFILES = $(wildcard *.py) $(wildcard ../*.py)

ALL: ./tags lint

lint: $(PYFILES)
	mypy --check-untyped-defs $^
	ruff check $^

./tags: $(PYFILES)
	ctags --languages=python --python-kinds=-i -f $@ $^

clean:
	rm -f tags
