PYTHONPATH1      := $(abs_top_srcdir)/tools/lirc-setup
PYTHONPATH2      := $(abs_top_srcdir)/lib/.libs:$(abs_top_srcdir)/lib
PYTHONPATH       := $(PYTHONPATH1):$(PYTHONPATH2)
PYLINT           = python3-pylint
pylint_template  = {path}:{line}: [{msg_id}({symbol}), {obj}] {msg}

py_source        = lirc/*.py


pep8:   $(py_source)
	python3-pep8 --config=./pep8.conf $?

force-pylint: .phony
	rm .pylint-stamp
	$(MAKE) pylint
py-source:

pylint: .pylint-stamp
.pylint-stamp: $(py_source)
	-PYTHONPATH=$(PYTHONPATH) $(PYLINT) --rcfile=pylint.conf \
	--msg-template='$(pylint_template)' $? && touch $@

.phony:
