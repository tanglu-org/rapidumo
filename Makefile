PREFIX := /usr/local

install: $(scripts)
	echo "IMPORTANT! We don't really install anything, we just create symlinks."
	ln -sf $(shell readlink -f ./scripts/synchrotron) $(DESTDIR)/$(PREFIX)/bin/synchrotron
	ln -sf $(shell readlink -f ./scripts/rapidumo) $(DESTDIR)/$(PREFIX)/bin/rapidumo
	ln -sf $(shell readlink -f ./autorebuild/exec-autorebuild.sh) $(DESTDIR)/$(PREFIX)/bin/trigger-pkg-rebuild

clean:
	rm -f *.pyc

.PHONY: install clean
