package io.github.killbus.statisticsboard;

import java.util.List;
import java.util.Locale;
import java.util.stream.Stream;
import org.bukkit.entity.Player;
import org.mvplugins.multiverse.core.world.WorldManager;
import org.mvplugins.multiverse.inventories.config.InventoriesConfig;
import org.mvplugins.multiverse.inventories.profile.group.WorldGroup;
import org.mvplugins.multiverse.inventories.profile.group.WorldGroupManager;
import org.mvplugins.multiverse.inventories.share.Sharables;
import org.mvplugins.multiverse.inventories.util.Perm;

final class StatisticsScopeResolver {
    private final InventoriesConfig config;
    private final WorldGroupManager groups;
    private final WorldManager worlds;

    StatisticsScopeResolver(InventoriesConfig config, WorldGroupManager groups, WorldManager worlds) {
        this.config = config;
        this.groups = groups;
        this.worlds = worlds;
    }

    Resolution resolve(Player player) {
        String world = player.getWorld().getName();
        if (!config.getActiveOptionalShares().contains(Sharables.GAME_STATISTICS)) {
            return Resolution.rejected("game_statistics is inactive");
        }
        if (config.getEnableBypassPermissions()) {
            if (Perm.BYPASS_WORLD.hasBypass(player, world)
                    || groups.getGroups().stream().anyMatch(group -> Perm.BYPASS_GROUP.hasBypass(player, group.getName()))) {
                return Resolution.rejected("statistics bypass permission");
            }
            for (String registered : Stream.concat(worlds.getLoadedWorlds().stream().map(loaded -> loaded.getName()),
                    worlds.getUnloadedWorlds().stream().map(unloaded -> unloaded.getName())).distinct().toList()) {
                if (Perm.BYPASS_WORLD.hasBypass(player, registered)) {
                    return Resolution.rejected("statistics bypass permission");
                }
            }
            if (config.getEnableGamemodeShareHandling()) {
                for (var mode : org.bukkit.GameMode.values()) {
                    if (Perm.BYPASS_GAME_MODE.hasBypass(player, mode.name().toLowerCase(Locale.ROOT))) {
                        return Resolution.rejected("statistics gamemode bypass permission");
                    }
                }
            }
        }
        List<WorldGroup> memberships = groups.getGroupsForWorld(world);
        if (memberships.stream().anyMatch(group -> group.getDisabledShares().contains(Sharables.GAME_STATISTICS))) {
            return Resolution.rejected("game_statistics is disabled for this world");
        }
        List<WorldGroup> applicable = memberships.stream()
                .filter(group -> group.getApplicableShares().contains(Sharables.GAME_STATISTICS)).toList();
        if (applicable.size() > 1) {
            return Resolution.rejected("overlapping game_statistics groups");
        }
        if (applicable.isEmpty() && memberships.isEmpty() && !config.getUseOptionalsForUngroupedWorlds()) {
            return Resolution.rejected("ungrouped optional statistics are inactive");
        }
        String scope = applicable.isEmpty() ? "world:" + world.toLowerCase(Locale.ROOT)
                : "group:" + applicable.getFirst().getName().toLowerCase(Locale.ROOT);
        if (config.getEnableGamemodeShareHandling()) {
            scope += ":gamemode:" + player.getGameMode().name();
        }
        return new Resolution(scope, null);
    }

    record Resolution(String scope, String reason) {
        static Resolution rejected(String reason) {
            return new Resolution(null, reason);
        }
    }
}
