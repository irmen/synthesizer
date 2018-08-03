.PHONY: all dist install upload clean test check lint

all:
	@echo "targets include dist, upload, install, clean, lint"

dist:
	python setup.py sdist bdist_wheel
	@echo "Look in the dist/ directory"

upload: dist
	@echo "Uploading to Pypi using twine...."
	twine upload dist/*

install:
	python setup.py install

lint:
	pycodestyle
	mypy synthplayer

clean:
	@echo "Removing tox dirs, logfiles, .pyo/.pyc files..."
	find . -name __pycache__ -print0 | xargs -0 rm -rf
	find . -name \*_log -print0 | xargs -0  rm -f
	find . -name \*.log -print0 | xargs -0  rm -f
	find . -name \*.pyo -print0 | xargs -0  rm -f
	find . -name \*.pyc -print0 | xargs -0  rm -f
	find . -name \*.class -print0 | xargs -0  rm -f
	find . -name \*.DS_Store -print0 | xargs -0  rm -f
	find . -name TEST-*.xml -print0 | xargs -0  rm -f
	find . -name TestResult.xml -print0 | xargs -0  rm -f
	rm -rf build dist .directory *.egg-info MANIFEST
	rm -rf .tox .eggs .mypy_cache .pytest_cache
	find . -name  '.#*' -print0 | xargs -0  rm -f
	find . -name  '#*#' -print0 | xargs -0  rm -f
	@echo "clean!"
