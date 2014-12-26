PREFIX := /usr/local

install: $(scripts)
	echo "IMPORTANT! We don't really install anything, we just create a symlink."
	ln -sf $(shell readlink -f ./synchrotron/sync-debian-package.py) $(DESTDIR)/$(PREFIX)/bin/sync-debian-package
	ln -sf $(shell readlink -f ./autorebuild/exec-autorebuild.sh) $(DESTDIR)/$(PREFIX)/bin/trigger-pkg-rebuild
	ln -sf $(shell readlink -f ./rapidumo.py) $(DESTDIR)/$(PREFIX)/bin/rapidumo

clean:
	rm -f *.pyc

.PHONY: install clean
