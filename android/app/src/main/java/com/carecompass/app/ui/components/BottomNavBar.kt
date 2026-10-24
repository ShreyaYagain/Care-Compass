package com.carecompass.app.ui.components

import androidx.compose.foundation.layout.heightIn
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.CalendarMonth
import androidx.compose.material.icons.filled.Home
import androidx.compose.material.icons.filled.Schedule
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.carecompass.app.R
import com.carecompass.app.ui.theme.PrimaryBlue

enum class NavigationTab(val route: String) {
    HOME("home_tab"),
    HISTORY("history_tab"),
    BOOKINGS("bookings_tab")
}

data class BottomNavItem(
    val tab: NavigationTab,
    val icon: ImageVector,
    val labelEnRes: Int,
    val labelHiRes: Int,
    val labelHinglishRes: Int
)

val BOTTOM_NAV_ITEMS = listOf(
    BottomNavItem(
        tab = NavigationTab.HOME,
        icon = Icons.Default.Home,
        labelEnRes = R.string.nav_home_en,
        labelHiRes = R.string.nav_home_hi,
        labelHinglishRes = R.string.nav_home_hinglish
    ),
    BottomNavItem(
        tab = NavigationTab.HISTORY,
        icon = Icons.Default.Schedule,
        labelEnRes = R.string.nav_history_en,
        labelHiRes = R.string.nav_history_hi,
        labelHinglishRes = R.string.nav_history_hinglish
    ),
    BottomNavItem(
        tab = NavigationTab.BOOKINGS,
        icon = Icons.Default.CalendarMonth,
        labelEnRes = R.string.nav_bookings_en,
        labelHiRes = R.string.nav_bookings_hi,
        labelHinglishRes = R.string.nav_bookings_hinglish
    )
)

@Composable
fun CareCompassBottomBar(
    selectedTab: NavigationTab,
    onTabSelected: (NavigationTab) -> Unit,
    selectedLanguage: String,
    modifier: Modifier = Modifier
) {
    NavigationBar(
        modifier = modifier.heightIn(min = 68.dp),
        containerColor = Color.White,
        tonalElevation = 6.dp
    ) {
        BOTTOM_NAV_ITEMS.forEach { item ->
            val isSelected = selectedTab == item.tab
            val labelText = when (selectedLanguage) {
                "hi" -> stringResource(item.labelHiRes)
                "hinglish" -> stringResource(item.labelHinglishRes)
                else -> stringResource(item.labelEnRes)
            }

            NavigationBarItem(
                selected = isSelected,
                onClick = { onTabSelected(item.tab) },
                icon = {
                    Icon(
                        imageVector = item.icon,
                        contentDescription = labelText
                    )
                },
                label = {
                    Text(
                        text = labelText,
                        fontSize = 14.sp,
                        fontWeight = if (isSelected) FontWeight.Bold else FontWeight.Medium
                    )
                },
                alwaysShowLabel = true,
                colors = NavigationBarItemDefaults.colors(
                    selectedIconColor = Color.White,
                    selectedTextColor = PrimaryBlue,
                    indicatorColor = PrimaryBlue,
                    unselectedIconColor = Color(0xFF64748B),
                    unselectedTextColor = Color(0xFF64748B)
                )
            )
        }
    }
}
