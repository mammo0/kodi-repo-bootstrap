<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<addon id="{addonid}" name="{reponame}" version="{addonversion}" provider-name="{addonauthor}">
    <requires>
        <import addon="xbmc.addon" version="12.0.0"/>
    </requires>
    <extension point="xbmc.addon.repository" name="{reponame}">
        <dir>
            <info compressed="false">{repourl}/addons.xml</info>
            <checksum>{repourl}/addons.xml.md5</checksum>
            <datadir zip="true">{repourl}/</datadir>
            <hashes>false</hashes>
        </dir>
    </extension>
    <extension point="xbmc.addon.metadata">
        <summary>{addonsummary}</summary>
        <description>{addondescription}</description>
        <platform>all</platform>
    </extension>
</addon>
