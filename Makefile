all:
	@echo "Targets"
	@echo "  settings    copy config/root/vars_config.tf into all OpenTofu root projects"
	@echo "  designkit-dev  preview the Loginapp styling (designkit/src) in the browser, live reload"
	@echo "  designkit   build the Loginapp styling and copy the zip into the IAM template (iam/)"
	@echo "              DESIGNKIT=<path of the Airlock IAM Loginapp Design Kit> (special download)"

.PHONY: settings
settings:
	make -C 01-infrastructure
	make -C 02-talos
	make -C 03-argocd

# Airlock IAM Loginapp Design Kit (not part of this repository - special download matching the
# IAM version), sources in designkit/src
DESIGNKIT ?= ../designkit/airlock-iam-loginapp-design-kit-8.7.0
UI_ZIP    := airlock-iam-loginapp-rest-ui-customizations.zip

.PHONY: designkit-dev
designkit-dev:
	$(DESIGNKIT)/sdk dev -d $(CURDIR)/designkit

.PHONY: designkit
designkit:
	$(DESIGNKIT)/sdk build -d $(CURDIR)/designkit
	cp designkit/build/$(UI_ZIP) iam/$(UI_ZIP)
	@ls -l iam/$(UI_ZIP)
