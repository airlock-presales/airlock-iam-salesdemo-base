PLATFORMS = $(notdir $(wildcard platforms/*))

all: $(addprefix platforms/,$(addsuffix /vars_config.tf,$(PLATFORMS)))

platforms/%/vars_config.tf: ../config/root/vars_config.tf
	cp $< $@
